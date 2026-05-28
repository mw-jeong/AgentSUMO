"""
XML to SQLite converter for SUMO simulation results.
"""

import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, Optional
import logging
import datetime
import re

logger = logging.getLogger("agentsumo.xml_to_sqlite")


class XMLToSQLiteConverter:
    """Convert SUMO XML results to SQLite database"""
    
    def convert_simulation_results(
        self,
        tripinfo_xml: str,
        edgedata_xml: str,
        edgedata_emission_xml: str,
        output_db: str,
        simulation_id: str = None,
        net_file: str = None,
        route_file: str = None,
        description: str = None,
        summary_xml: str = None
    ) -> Dict[str, Any]:
        """Convert XML to SQLite with simulation_id"""
        conn = None
        db_exists_before = Path(output_db).exists()

        try:
            if not simulation_id:
                # Include milliseconds to avoid collision in fast consecutive simulations
                now = datetime.datetime.now()
                timestamp = now.strftime("%Y%m%d_%H%M%S") + f"_{now.microsecond // 1000:03d}"
                simulation_id = f"sim_{timestamp}"
            
            logger.info(f"Converting to SQLite: {simulation_id}")
            
            # Open/create DB
            db_exists = Path(output_db).exists()
            conn = sqlite3.connect(output_db)

            if not db_exists:
                self._create_schema(conn)
            else:
                # Ensure new tables exist in older DBs
                self._ensure_new_tables(conn)
                # Prevent duplicate imports of the same simulation data
                try:
                    existing = conn.execute(
                        "SELECT simulation_id, description FROM simulations WHERE net_file=?",
                        (net_file,)
                    ).fetchall()

                    for existing_id, existing_desc in existing:
                        if existing_id == simulation_id:
                            # Exact same ID already exists — skip
                            logger.info(f"Duplicate: {simulation_id} already exists, skipping")
                            conn.close()
                            return {
                                "status": "skipped", "db_file": str(output_db),
                                "simulation_id": existing_id,
                                "message": f"Already imported as {existing_id}"
                            }

                        # Case: auto-generated ID exists, now called with meaningful ID
                        # → delete the auto entry, proceed with the good one
                        if existing_id.startswith("sim_") and not simulation_id.startswith("sim_"):
                            logger.info(f"Replacing auto-generated {existing_id} with {simulation_id}")
                            conn.execute("DELETE FROM trips WHERE simulation_id=?", (existing_id,))
                            conn.execute("DELETE FROM edge_metrics WHERE simulation_id=?", (existing_id,))
                            conn.execute("DELETE FROM simulations WHERE simulation_id=?", (existing_id,))
                            conn.commit()

                        # Case: meaningful ID exists, now called with auto-generated ID
                        # → skip the auto entry
                        if not existing_id.startswith("sim_") and simulation_id.startswith("sim_"):
                            logger.info(f"Skipping auto-generated {simulation_id}, already have {existing_id}")
                            conn.close()
                            return {
                                "status": "skipped", "db_file": str(output_db),
                                "simulation_id": existing_id,
                                "message": f"Already imported as {existing_id}"
                            }
                except Exception:
                    pass  # Table might not exist yet, continue normally

            # Import data
            edge_info_count = self._import_edge_info(conn, net_file, simulation_id)
            trip_count = self._import_tripinfo(conn, tripinfo_xml, simulation_id)
            vehicle_info_count = self._import_vehicle_info(
                conn, tripinfo_xml, net_file, simulation_id
            )
            edge_count = self._import_edgedata(conn, edgedata_xml, edgedata_emission_xml, simulation_id)
            summary_count = self._import_summary(conn, summary_xml, simulation_id) if summary_xml else 0

            # Save metadata
            conn.execute("""
                INSERT INTO simulations VALUES (?, ?, ?, ?, ?, ?)
            """, (simulation_id, datetime.datetime.now().isoformat(), trip_count, net_file, route_file, description))

            if not db_exists:
                self._create_indexes(conn)

            conn.commit()
            conn.close()

            return {
                "status": "success",
                "db_file": output_db,
                "simulation_id": simulation_id,
                "metadata": {
                    "trip_count": trip_count,
                    "edge_count": edge_count,
                    "edge_info_count": edge_info_count,
                    "vehicle_info_count": vehicle_info_count,
                    "summary_count": summary_count
                }
            }
        except Exception as e:
            # 에러 발생 시 연결 정리
            if conn:
                try:
                    conn.close()
                except:
                    pass
            
            # 에러 발생 시 새로 생성된 빈 DB 파일 삭제
            if not db_exists_before and Path(output_db).exists():
                try:
                    # 파일이 비어있거나 스키마만 있는 경우 삭제
                    file_size = Path(output_db).stat().st_size
                    if file_size < 1024:  # 1KB 미만이면 빈 파일로 간주
                        Path(output_db).unlink()
                        logger.warning(f"에러 발생으로 인해 빈 DB 파일 삭제: {output_db}")
                except Exception as cleanup_error:
                    logger.warning(f"빈 DB 파일 삭제 실패: {cleanup_error}")
            
            return {"status": "error", "message": str(e)}
    
    def _ensure_new_tables(self, conn):
        """Create new tables if they don't exist (migration for older DBs)."""
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

        if "edge_info" not in tables:
            conn.execute("""CREATE TABLE edge_info (
                simulation_id TEXT,
                edge_id TEXT,
                road_name TEXT,
                length REAL,
                num_lanes INTEGER,
                speed_limit REAL,
                PRIMARY KEY (simulation_id, edge_id)
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ei_road_name ON edge_info(road_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ei_length ON edge_info(length)")
            logger.info("Migrated: edge_info table created in existing DB")

        if "vehicle_info" not in tables:
            conn.execute("""CREATE TABLE vehicle_info (
                simulation_id TEXT,
                vehicle_id TEXT,
                vehicle_type TEXT,
                fuel_type TEXT,
                origin_edge TEXT,
                destination_edge TEXT,
                origin_road TEXT,
                destination_road TEXT,
                PRIMARY KEY (simulation_id, vehicle_id)
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_vi_fuel ON vehicle_info(fuel_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_vi_origin ON vehicle_info(origin_road)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_vi_dest ON vehicle_info(destination_road)")
            logger.info("Migrated: vehicle_info table created in existing DB")

        if "network_state" not in tables:
            conn.execute("""CREATE TABLE network_state (
                simulation_id TEXT,
                time REAL,
                loaded INTEGER,
                inserted INTEGER,
                running INTEGER,
                waiting INTEGER,
                ended INTEGER,
                arrived INTEGER,
                halting INTEGER,
                meanSpeed REAL,
                meanSpeedRelative REAL,
                meanTravelTime REAL,
                meanWaitingTime REAL,
                teleports INTEGER,
                collisions INTEGER,
                PRIMARY KEY (simulation_id, time)
            )""")
            logger.info("Migrated: network_state table created in existing DB")

        conn.commit()

    def _create_schema(self, conn):
        """Create schema - tripinfo/edgedata XML의 모든 속성을 개별 컬럼으로 저장"""
        conn.execute("CREATE TABLE simulations (simulation_id TEXT PRIMARY KEY, created_at TEXT, vehicle_count INTEGER, net_file TEXT, route_file TEXT, description TEXT)")

        # trips 테이블: tripinfo XML의 모든 속성
        conn.execute("""CREATE TABLE trips (
            simulation_id TEXT,
            trip_id TEXT,
            depart REAL,
            departLane TEXT,
            departPos REAL,
            departSpeed REAL,
            departDelay REAL,
            arrival REAL,
            arrivalLane TEXT,
            arrivalPos REAL,
            arrivalSpeed REAL,
            duration REAL,
            routeLength REAL,
            waitingTime REAL,
            waitingCount INTEGER,
            stopTime REAL,
            timeLoss REAL,
            rerouteNo INTEGER,
            devices TEXT,
            vType TEXT,
            speedFactor REAL,
            vaporized TEXT,
            CO_abs REAL,
            CO2_abs REAL,
            HC_abs REAL,
            PMx_abs REAL,
            NOx_abs REAL,
            fuel_abs REAL,
            electricity_abs REAL,
            PRIMARY KEY (simulation_id, trip_id)
        )""")

        # vehicle_info 테이블: 차량 메타데이터 (type, fuel, OD)
        conn.execute("""CREATE TABLE vehicle_info (
            simulation_id TEXT,
            vehicle_id TEXT,
            vehicle_type TEXT,
            fuel_type TEXT,
            origin_edge TEXT,
            destination_edge TEXT,
            origin_road TEXT,
            destination_road TEXT,
            PRIMARY KEY (simulation_id, vehicle_id)
        )""")

        # edge_info 테이블: 네트워크 edge 속성 (road_name, length 등)
        conn.execute("""CREATE TABLE edge_info (
            simulation_id TEXT,
            edge_id TEXT,
            road_name TEXT,
            length REAL,
            num_lanes INTEGER,
            speed_limit REAL,
            PRIMARY KEY (simulation_id, edge_id)
        )""")

        # edge_metrics 테이블: edgedata XML의 모든 속성
        conn.execute("""CREATE TABLE edge_metrics (
            simulation_id TEXT,
            edge_id TEXT,
            interval_begin REAL,
            interval_end REAL,
            sampledSeconds REAL,
            traveltime REAL,
            overlapTraveltime REAL,
            density REAL,
            laneDensity REAL,
            occupancy REAL,
            waitingTime REAL,
            timeLoss REAL,
            speed REAL,
            speedRelative REAL,
            departed INTEGER,
            arrived INTEGER,
            entered INTEGER,
            left INTEGER,
            laneChangedFrom INTEGER,
            laneChangedTo INTEGER,
            CO_abs REAL,
            CO2_abs REAL,
            HC_abs REAL,
            PMx_abs REAL,
            NOx_abs REAL,
            fuel_abs REAL,
            electricity_abs REAL,
            CO_normed REAL,
            CO2_normed REAL,
            HC_normed REAL,
            PMx_normed REAL,
            NOx_normed REAL,
            fuel_normed REAL,
            electricity_normed REAL,
            CO_perVeh REAL,
            CO2_perVeh REAL,
            HC_perVeh REAL,
            PMx_perVeh REAL,
            NOx_perVeh REAL,
            fuel_perVeh REAL,
            electricity_perVeh REAL,
            PRIMARY KEY (simulation_id, edge_id, interval_begin)
        )""")

        # network_state 테이블: summary.xml의 시간별 네트워크 집계
        conn.execute("""CREATE TABLE network_state (
            simulation_id TEXT,
            time REAL,
            loaded INTEGER,
            inserted INTEGER,
            running INTEGER,
            waiting INTEGER,
            ended INTEGER,
            arrived INTEGER,
            halting INTEGER,
            meanSpeed REAL,
            meanSpeedRelative REAL,
            meanTravelTime REAL,
            meanWaitingTime REAL,
            teleports INTEGER,
            collisions INTEGER,
            PRIMARY KEY (simulation_id, time)
        )""")

    def _import_edge_info(self, conn, net_file: Optional[str], sim_id: str) -> int:
        """Import edge metadata (road_name, length, etc.) from network file."""
        if not net_file or not Path(net_file).exists():
            logger.warning(f"net_file not available, skipping edge_info import")
            return 0

        try:
            import sumolib
            net = sumolib.net.readNet(net_file)
        except Exception as e:
            logger.warning(f"Failed to read net_file for edge_info: {e}")
            return 0

        count = 0
        for edge in net.getEdges():
            edge_id = edge.getID()
            road_name = edge.getName() or None
            length = round(edge.getLength(), 2)
            num_lanes = edge.getLaneNumber()
            speed_limit = round(edge.getSpeed() * 3.6, 1)  # m/s → km/h

            conn.execute(
                "INSERT OR IGNORE INTO edge_info VALUES (?, ?, ?, ?, ?, ?)",
                (sim_id, edge_id, road_name, length, num_lanes, speed_limit)
            )
            count += 1

        logger.info(f"Imported edge_info: {count} edges")
        return count

    def _import_vehicle_info(
        self, conn, tripinfo_xml: str, net_file: Optional[str], sim_id: str
    ) -> int:
        """Import vehicle metadata from tripinfo XML + network file."""
        # Build edge_id → road_name lookup from already-imported edge_info
        road_name_map = {}
        try:
            rows = conn.execute(
                "SELECT edge_id, road_name FROM edge_info WHERE simulation_id = ?",
                (sim_id,)
            ).fetchall()
            road_name_map = {r[0]: r[1] for r in rows}
        except Exception:
            pass

        # Build vType → fuel_type mapping from vehicle_types.add.xml
        fuel_type_map = {}
        if net_file:
            vtype_file = Path(net_file).parent / "vehicle_types.add.xml"
            if vtype_file.exists():
                fuel_type_map = self._parse_vehicle_types(str(vtype_file))

        count = 0
        for event, elem in ET.iterparse(tripinfo_xml, events=('end',)):
            if elem.tag == 'tripinfo':
                vehicle_id = elem.get('id', '')
                vtype = elem.get('vType', '')
                depart_lane = elem.get('departLane', '')
                arrival_lane = elem.get('arrivalLane', '')

                # Extract edge from lane (e.g., "edge_id_0" → "edge_id")
                origin_edge = depart_lane.rsplit('_', 1)[0] if depart_lane else None
                dest_edge = arrival_lane.rsplit('_', 1)[0] if arrival_lane else None

                origin_road = road_name_map.get(origin_edge) if origin_edge else None
                dest_road = road_name_map.get(dest_edge) if dest_edge else None

                fuel_type = fuel_type_map.get(vtype, self._infer_fuel_type(vtype))

                conn.execute(
                    "INSERT OR IGNORE INTO vehicle_info VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (sim_id, vehicle_id, vtype, fuel_type,
                     origin_edge, dest_edge, origin_road, dest_road)
                )
                count += 1
                elem.clear()

        logger.info(f"Imported vehicle_info: {count} vehicles")
        return count

    @staticmethod
    def _parse_vehicle_types(vtype_file: str) -> dict:
        """Parse vehicle_types.add.xml → {vType_id: fuel_type} mapping."""
        fuel_map = {}
        try:
            tree = ET.parse(vtype_file)
            for vtype in tree.findall('.//vType'):
                vid = vtype.get('id', '')
                emission_class = vtype.get('emissionClass', '')
                fuel_map[vid] = XMLToSQLiteConverter._classify_fuel(emission_class)
        except Exception:
            pass
        return fuel_map

    @staticmethod
    def _classify_fuel(emission_class: str) -> str:
        """Classify fuel type from SUMO emissionClass string."""
        ec = emission_class.lower()
        if not ec or ec == 'zero' or 'energy' in ec or 'electric' in ec:
            return 'electric'
        if '_d_' in ec or 'diesel' in ec:
            return 'diesel'
        if '_g_' in ec or 'gasoline' in ec or 'petrol' in ec:
            return 'gasoline'
        return 'unknown'

    @staticmethod
    def _infer_fuel_type(vtype: str) -> str:
        """Infer fuel type from vType name when vehicle_types.add.xml is unavailable."""
        vt = vtype.lower()
        if 'electric' in vt or 'ev' in vt or 'bev' in vt:
            return 'electric'
        if 'diesel' in vt:
            return 'diesel'
        return 'gasoline'

    def _import_tripinfo(self, conn, xml_file, sim_id):
        """Import trips - tripinfo XML의 모든 속성을 개별 컬럼으로 저장"""
        count = 0
        for event, elem in ET.iterparse(xml_file, events=('end',)):
            if elem.tag == 'tripinfo':
                attrs = elem.attrib

                def safe_float(key, default=0.0):
                    val = attrs.get(key)
                    if val is None or val == '':
                        return default
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        return default

                def safe_int(key, default=0):
                    val = attrs.get(key)
                    if val is None or val == '':
                        return default
                    try:
                        return int(float(val))
                    except (ValueError, TypeError):
                        return default

                # Parse emissions child element
                emissions_elem = elem.find('emissions')
                if emissions_elem is not None:
                    em = emissions_elem.attrib
                else:
                    em = {}

                def em_float(key):
                    val = em.get(key)
                    if val is None or val == '':
                        return 0.0
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        return 0.0

                # INSERT 실행 (29 컬럼)
                conn.execute("""INSERT INTO trips VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )""", (
                    sim_id,
                    attrs.get('id', ''),
                    safe_float('depart'),
                    attrs.get('departLane', ''),
                    safe_float('departPos'),
                    safe_float('departSpeed'),
                    safe_float('departDelay'),
                    safe_float('arrival'),
                    attrs.get('arrivalLane', ''),
                    safe_float('arrivalPos'),
                    safe_float('arrivalSpeed'),
                    safe_float('duration'),
                    safe_float('routeLength'),
                    safe_float('waitingTime'),
                    safe_int('waitingCount'),
                    safe_float('stopTime'),
                    safe_float('timeLoss'),
                    safe_int('rerouteNo'),
                    attrs.get('devices', ''),
                    attrs.get('vType', ''),
                    safe_float('speedFactor'),
                    attrs.get('vaporized', ''),
                    em_float('CO_abs'),
                    em_float('CO2_abs'),
                    em_float('HC_abs'),
                    em_float('PMx_abs'),
                    em_float('NOx_abs'),
                    em_float('fuel_abs'),
                    em_float('electricity_abs'),
                ))
                count += 1
                elem.clear()
        return count
    
    def _import_edgedata(self, conn, edgedata_xml, emission_xml, sim_id):
        """Import edges - edgedata XML의 모든 속성을 개별 컬럼으로 저장"""
        # Load emission data first
        emission_data = {}
        if emission_xml and Path(emission_xml).exists():
            for event, elem in ET.iterparse(emission_xml, events=('end',)):
                if elem.tag == 'interval':
                    for edge in elem.findall('edge'):
                        emission_data[edge.get('id', '')] = edge.attrib
                    elem.clear()

        count = 0
        for event, elem in ET.iterparse(edgedata_xml, events=('end',)):
            if elem.tag == 'interval':
                interval_begin = float(elem.get('begin', 0))
                interval_end = float(elem.get('end', 0))

                for edge in elem.findall('edge'):
                    attrs = edge.attrib

                    def safe_float(key, default=0.0):
                        val = attrs.get(key)
                        if val is None or val == '':
                            return default
                        try:
                            return float(val)
                        except (ValueError, TypeError):
                            return default

                    def safe_int(key, default=0):
                        val = attrs.get(key)
                        if val is None or val == '':
                            return default
                        try:
                            return int(float(val))
                        except (ValueError, TypeError):
                            return default

                    # Look up emission data for this edge
                    edge_id = attrs.get('id', '')
                    em = emission_data.get(edge_id, {})

                    def em_float(key, default=0.0):
                        val = em.get(key)
                        if val is None or val == '':
                            return default
                        try:
                            return float(val)
                        except (ValueError, TypeError):
                            return default

                    # INSERT 실행 (41 컬럼)
                    conn.execute("""INSERT INTO edge_metrics VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )""", (
                        sim_id,
                        edge_id,
                        interval_begin,
                        interval_end,
                        safe_float('sampledSeconds'),
                        safe_float('traveltime'),
                        safe_float('overlapTraveltime'),
                        safe_float('density'),
                        safe_float('laneDensity'),
                        safe_float('occupancy'),
                        safe_float('waitingTime'),
                        safe_float('timeLoss'),
                        safe_float('speed'),
                        safe_float('speedRelative'),
                        safe_int('departed'),
                        safe_int('arrived'),
                        safe_int('entered'),
                        safe_int('left'),
                        safe_int('laneChangedFrom'),
                        safe_int('laneChangedTo'),
                        em_float('CO_abs'),
                        em_float('CO2_abs'),
                        em_float('HC_abs'),
                        em_float('PMx_abs'),
                        em_float('NOx_abs'),
                        em_float('fuel_abs'),
                        em_float('electricity_abs'),
                        em_float('CO_normed'),
                        em_float('CO2_normed'),
                        em_float('HC_normed'),
                        em_float('PMx_normed'),
                        em_float('NOx_normed'),
                        em_float('fuel_normed'),
                        em_float('electricity_normed'),
                        em_float('CO_perVeh'),
                        em_float('CO2_perVeh'),
                        em_float('HC_perVeh'),
                        em_float('PMx_perVeh'),
                        em_float('NOx_perVeh'),
                        em_float('fuel_perVeh'),
                        em_float('electricity_perVeh'),
                    ))
                    count += 1
                elem.clear()

        return count

    def _import_summary(self, conn, summary_xml: str, sim_id: str) -> int:
        """Import summary.xml — network-wide time-series metrics."""
        if not summary_xml or not Path(summary_xml).exists():
            logger.warning(f"summary_xml not available, skipping import")
            return 0

        count = 0
        # Column order must match CREATE TABLE:
        # simulation_id, time, loaded, inserted, running, waiting, ended,
        # arrived, halting, meanSpeed, meanSpeedRelative, meanTravelTime,
        # meanWaitingTime, teleports, collisions
        int_fields_pre = ['loaded', 'inserted', 'running', 'waiting', 'ended', 'arrived', 'halting']
        float_fields = ['meanSpeed', 'meanSpeedRelative', 'meanTravelTime', 'meanWaitingTime']
        int_fields_post = ['teleports', 'collisions']

        for event, elem in ET.iterparse(summary_xml, events=("end",)):
            if elem.tag == "step":
                time_val = float(elem.get("time", 0))

                pre_vals = [int(elem.get(f, 0)) for f in int_fields_pre]
                real_vals = [round(float(elem.get(f, 0)), 4) if elem.get(f) is not None else None for f in float_fields]
                post_vals = [int(elem.get(f, 0)) for f in int_fields_post]

                conn.execute(
                    """INSERT OR IGNORE INTO network_state VALUES
                       (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (sim_id, time_val, *pre_vals, *real_vals, *post_vals)
                )
                count += 1
                elem.clear()

        logger.info(f"Imported network_state: {count} time steps")
        return count

    def _create_indexes(self, conn):
        """Create indexes"""
        # edge_info 인덱스
        conn.execute("CREATE INDEX idx_ei_road_name ON edge_info(road_name)")
        conn.execute("CREATE INDEX idx_ei_length ON edge_info(length)")

        # edge_metrics 인덱스
        conn.execute("CREATE INDEX idx_density ON edge_metrics(density DESC)")
        conn.execute("CREATE INDEX idx_sim_edge ON edge_metrics(simulation_id, edge_id)")
        conn.execute("CREATE INDEX idx_interval ON edge_metrics(interval_begin, interval_end)")
        conn.execute("CREATE INDEX idx_speed ON edge_metrics(speed DESC)")
        conn.execute("CREATE INDEX idx_waitingTime ON edge_metrics(waitingTime DESC)")
        
        # vehicle_info 인덱스
        conn.execute("CREATE INDEX idx_vi_fuel ON vehicle_info(fuel_type)")
        conn.execute("CREATE INDEX idx_vi_origin ON vehicle_info(origin_road)")
        conn.execute("CREATE INDEX idx_vi_dest ON vehicle_info(destination_road)")

        # trips 인덱스
        conn.execute("CREATE INDEX idx_trips_duration ON trips(duration DESC)")
        conn.execute("CREATE INDEX idx_trips_timeLoss ON trips(timeLoss DESC)")
        conn.execute("CREATE INDEX idx_trips_sim ON trips(simulation_id)")
        conn.execute("CREATE INDEX idx_trips_depart ON trips(depart)")
        conn.execute("CREATE INDEX idx_trips_arrival ON trips(arrival)")

        # network_state 인덱스
        conn.execute("CREATE INDEX idx_ss_sim ON network_state(simulation_id)")


def extract_tag_from_xml(xml_file: str) -> str:
    """
    Extract base tag from filename, removing policy-specific suffixes.
    
    This ensures all simulations from the same baseline network use the same DB.
    
    Examples:
        gangnam_station.net_tripinfo_xxx.xml → gangnam_station
    """
    filename = Path(xml_file).stem
    
    # Remove SUMO output suffixes
    filename = filename.replace('_tripinfo', '').replace('_netstate', '').replace('_emission', '').replace('.net', '')
    
    # Remove timestamps (all 8digit_6digit patterns)
    filename = re.sub(r'_\d{8}_\d{6}', '', filename)
    
    # Remove policy-specific suffixes
    # Match: _policyname or _policyname_N (where N is a number)
    policy_keywords = ['speedlimit', 'reducelanes', 'edgeedit', 'tls', 'tls_adaptation', 'tls_offset']
    
    for keyword in policy_keywords:
        # Pattern: _keyword_anything or _keyword (at end or followed by _)
        filename = re.sub(rf'_{keyword}(_\d+)?.*$', '', filename)  # Remove from keyword onwards
    
    return filename
