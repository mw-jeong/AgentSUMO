"""
osm_http.py — Online OSM data acquisition for AgentSUMO.

Two paths:
  1. extract_osm_via_http(bbox, ...)        — small/medium bbox via Overpass.
  2. download_pbf_for_region(bbox, ...)     — large or offline-needed area;
                                              downloads Geofabrik region PBF
                                              (one-time cache) for use with osmium.

Replaces SUMO's osmGet.py for AgentSUMO's online fetch path.

Features
--------
- Explicit User-Agent (osmGet's default UA is rejected by Overpass mirrors with 406)
- Overpass mirror chain failover (primary -> alternatives on HTTP/timeout failure)
- gzip transport (Accept-Encoding) + optional gzip output
- Response size validation (eliminates osmGet's silent fail mode)
- Adaptive timeouts (fast primary, longer fallback)
- osmGet's default Overpass QL query (compatible with SUMO netconvert)
- Geofabrik region PBF download with cache + tqdm progress
"""

import gzip
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import httpx

try:
    from tqdm import tqdm
    _HAS_TQDM = True
except ImportError:
    _HAS_TQDM = False

logger = logging.getLogger("agentsumo_mcp.osm_http")


DEFAULT_USER_AGENT = (
    "AgentSUMO-MCP/0.1.0 (+https://github.com/mw-jeong/agentsumo-mcp)"
)

# Ordered mirror chain. Primary first; alternates tried on failure.
DEFAULT_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]

# Fast primary timeout so failover happens quickly when the main server
# is degraded; longer for subsequent mirrors to give them room.
PRIMARY_TIMEOUT_S = 60.0
FALLBACK_TIMEOUT_S = 300.0

# Below this size, treat the response as a silent failure (Overpass
# sometimes returns 200 with near-empty bodies on backend errors).
MIN_RESPONSE_BYTES = 1024

# Overpass server-side query timeout (not HTTP). Matches osmGet.py default.
OVERPASS_QUERY_TIMEOUT = 240


def _build_overpass_query(
    bbox: List[float], query_timeout: int = OVERPASS_QUERY_TIMEOUT
) -> str:
    """
    Build OQL XML query matching osmGet.py's default (no road-type filter).

    Returns nodes + ways + relations + their referenced members, which is
    what SUMO netconvert needs to build a complete drivable network.
    """
    west, south, east, north = bbox
    return (
        f'<osm-script timeout="{query_timeout}" element-limit="1073741824">\n'
        '    <union>\n'
        f'        <bbox-query n="{north}" s="{south}" w="{west}" e="{east}"/>\n'
        '        <recurse type="node-relation" into="rels"/>\n'
        '        <recurse type="node-way"/>\n'
        '        <recurse type="way-relation"/>\n'
        '    </union>\n'
        '    <union>\n'
        '        <item/>\n'
        '        <recurse type="way-node"/>\n'
        '    </union>\n'
        '    <print mode="body"/>\n'
        '</osm-script>'
    )


def _validate_bbox(bbox: List[float]) -> None:
    if len(bbox) != 4:
        raise ValueError(f"bbox must have 4 elements [W,S,E,N], got {bbox}")
    west, south, east, north = bbox
    if not (west < east and south < north):
        raise ValueError(
            f"Invalid bbox order: west={west}, east={east}, "
            f"south={south}, north={north}"
        )
    if not (-180 <= west <= 180 and -180 <= east <= 180):
        raise ValueError(f"Longitudes out of range: west={west}, east={east}")
    if not (-90 <= south <= 90 and -90 <= north <= 90):
        raise ValueError(f"Latitudes out of range: south={south}, north={north}")


def extract_osm_via_http(
    bbox: List[float],
    tag: str,
    output_path: Path,
    *,
    gzip_output: bool = False,
    mirrors: Optional[List[str]] = None,
    user_agent: str = DEFAULT_USER_AGENT,
) -> str:
    """
    Download OSM data via Overpass interpreter with mirror failover.

    Args:
        bbox:         [west, south, east, north] in WGS84 degrees
        tag:          prefix for output filename
        output_path:  directory for output (created if missing)
        gzip_output:  save as .osm.xml.gz (default False, plain .osm.xml)
        mirrors:      override of default mirror chain (testing/enterprise)
        user_agent:   User-Agent header (default app identifier + repo URL)

    Returns:
        Path to the downloaded OSM file (str, matching osmGet wrapper API).

    Raises:
        ValueError: invalid bbox
        RuntimeError: all mirrors exhausted without success
    """
    _validate_bbox(bbox)
    mirror_list = list(mirrors or DEFAULT_MIRRORS)
    output_path.mkdir(parents=True, exist_ok=True)

    query = _build_overpass_query(bbox)
    area_deg2 = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])

    if area_deg2 > 1.0:
        logger.warning(
            f"Large bbox area ({area_deg2:.2f} sq deg). May hit Overpass "
            f"element-limit. Consider local PBF + osmium at this scale."
        )

    headers = {
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip",  # httpx handles decompression automatically
    }

    last_error: Optional[str] = None
    for idx, url in enumerate(mirror_list):
        timeout = PRIMARY_TIMEOUT_S if idx == 0 else FALLBACK_TIMEOUT_S
        logger.info(
            f"OSM mirror {idx+1}/{len(mirror_list)}: {url} (timeout={timeout:.0f}s)"
        )

        try:
            resp = httpx.post(
                url,
                content=query,
                headers=headers,
                timeout=timeout,
            )
        except httpx.HTTPError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning(f"  -> failed ({last_error}); trying next mirror")
            continue

        if resp.status_code != 200:
            preview = resp.text[:200] if resp.text else "(empty)"
            last_error = f"HTTP {resp.status_code}: {preview!r}"
            logger.warning(f"  -> non-200 ({last_error}); trying next mirror")
            continue

        content = resp.content
        if len(content) < MIN_RESPONSE_BYTES:
            preview = resp.text[:200] if resp.text else "(empty)"
            last_error = f"Response too small ({len(content)} B): {preview!r}"
            logger.warning(f"  -> {last_error}; trying next mirror")
            continue

        if gzip_output:
            out_file = output_path / f"{tag}_bbox.osm.xml.gz"
            out_file.write_bytes(gzip.compress(content))
        else:
            out_file = output_path / f"{tag}_bbox.osm.xml"
            out_file.write_bytes(content)

        size_kb = out_file.stat().st_size / 1024
        logger.info(f"  -> wrote {out_file.name} ({size_kb:.1f} KB)")
        return str(out_file)

    raise RuntimeError(
        f"All {len(mirror_list)} Overpass mirrors failed. "
        f"Last error: {last_error}"
    )


# ===================================================== Geofabrik PBF download

GEOFABRIK_BASE = "https://download.geofabrik.de"

# bbox here is a generous WSEN match window for region identification, not
# the exact Geofabrik file extent. Adding a new region only needs an entry here.
REGIONS: Dict[str, Dict] = {
    "south-korea": {
        "bbox": [124, 33, 132, 39],
        "geofabrik_path": "asia",
        "est_size_mb": 270,
    },
    "new-york": {
        "bbox": [-80, 40, -71, 45],
        "geofabrik_path": "north-america/us",
        "est_size_mb": 470,
    },
    "california": {
        "bbox": [-125, 32, -114, 42],
        "geofabrik_path": "north-america/us",
        "est_size_mb": 1255,
    },
}


def default_data_dir() -> Path:
    """Resolve PBF cache directory: $AGENTSUMO_DATA_DIR or ~/.agentsumo/data."""
    env = os.environ.get("AGENTSUMO_DATA_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".agentsumo" / "data"


def identify_region(bbox: List[float]) -> Optional[Dict]:
    """Find the REGIONS entry whose bbox contains the center of input bbox."""
    center_lon = (bbox[0] + bbox[2]) / 2
    center_lat = (bbox[1] + bbox[3]) / 2
    for name, info in REGIONS.items():
        rw, rs, re_, rn = info["bbox"]
        if rw <= center_lon <= re_ and rs <= center_lat <= rn:
            return {**info, "name": name}
    return None


def _build_geofabrik_url(region: Dict) -> str:
    return f"{GEOFABRIK_BASE}/{region['geofabrik_path']}/{region['name']}-latest.osm.pbf"


def download_pbf_for_region(
    bbox: List[float],
    data_dir: Optional[Path] = None,
    *,
    chunk_size: int = 1024 * 1024,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Path:
    """
    Download Geofabrik PBF covering the region containing bbox center.

    Args:
        bbox:       [W, S, E, N] in WGS84 degrees
        data_dir:   PBF cache directory (default: ~/.agentsumo/data/)
        chunk_size: streaming chunk size in bytes
        user_agent: User-Agent header (app identifier + repo URL)

    Returns:
        Path to PBF file (cache hit if present, downloaded otherwise).

    Raises:
        ValueError:   bbox not covered by any known REGIONS entry
        RuntimeError: download failed (network error, HTTP error)
    """
    region = identify_region(bbox)
    if region is None:
        raise ValueError(
            f"bbox center ({(bbox[0]+bbox[2])/2:.3f}, {(bbox[1]+bbox[3])/2:.3f}) "
            f"not covered by any known Geofabrik region. "
            f"Supported: {list(REGIONS.keys())}"
        )

    data_dir = data_dir or default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    pbf_path = data_dir / f"{region['name']}-latest.osm.pbf"

    if pbf_path.exists():
        size_mb = pbf_path.stat().st_size / 1024 / 1024
        logger.info(f"PBF cache hit: {pbf_path.name} ({size_mb:.1f} MB)")
        return pbf_path

    url = _build_geofabrik_url(region)
    logger.info(
        f"Downloading {region['name']} PBF (~{region['est_size_mb']} MB) "
        f"from Geofabrik — one-time setup, saved to {data_dir}"
    )

    try:
        with httpx.stream(
            "GET", url,
            headers={"User-Agent": user_agent},
            follow_redirects=True,
            timeout=600.0,
        ) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", 0))

            with pbf_path.open("wb") as out:
                if _HAS_TQDM and total > 0:
                    pbar = tqdm(
                        total=total, unit="B", unit_scale=True,
                        desc=region["name"], leave=False,
                    )
                else:
                    pbar = None

                bytes_written = 0
                next_log_at = 50 * 1024 * 1024  # log every 50 MB if no tqdm

                for chunk in resp.iter_bytes(chunk_size=chunk_size):
                    out.write(chunk)
                    bytes_written += len(chunk)
                    if pbar:
                        pbar.update(len(chunk))
                    elif bytes_written >= next_log_at:
                        logger.info(
                            f"  {region['name']}: {bytes_written / 1024 / 1024:.0f} MB "
                            f"of {total / 1024 / 1024:.0f} MB"
                        )
                        next_log_at += 50 * 1024 * 1024

                if pbar:
                    pbar.close()
    except (httpx.HTTPError, OSError) as exc:
        # Don't leave a half-written file lying around
        if pbf_path.exists():
            pbf_path.unlink()
        raise RuntimeError(
            f"PBF download failed for {region['name']}: {exc}"
        ) from exc

    size_mb = pbf_path.stat().st_size / 1024 / 1024
    logger.info(f"PBF download complete: {pbf_path.name} ({size_mb:.1f} MB)")
    return pbf_path
