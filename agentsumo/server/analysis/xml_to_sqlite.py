"""
XML to SQLite converter for SUMO simulation results.
"""

import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any
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
        description: str = None
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
            
            # Import data
            trip_count = self._import_tripinfo(conn, tripinfo_xml, simulation_id)
            edge_count = self._import_edgedata(conn, edgedata_xml, edgedata_emission_xml, simulation_id)
            
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
                "metadata": {"trip_count": trip_count, "edge_count": edge_count}
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
            PRIMARY KEY (simulation_id, trip_id)
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
            PRIMARY KEY (simulation_id, edge_id, interval_begin)
        )""")
    
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

                # INSERT 실행 (22 컬럼)
                conn.execute("""INSERT INTO trips VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
                ))
                count += 1
                elem.clear()
        return count
    
    def _import_edgedata(self, conn, edgedata_xml, emission_xml, sim_id):
        """Import edges - edgedata XML의 모든 속성을 개별 컬럼으로 저장"""
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

                    # INSERT 실행 (20 컬럼)
                    conn.execute("""INSERT INTO edge_metrics VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )""", (
                        sim_id,
                        attrs.get('id', ''),
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
                    ))
                    count += 1
                elem.clear()

        return count
    
    def _create_indexes(self, conn):
        """Create indexes"""
        # edge_metrics 인덱스
        conn.execute("CREATE INDEX idx_density ON edge_metrics(density DESC)")
        conn.execute("CREATE INDEX idx_sim_edge ON edge_metrics(simulation_id, edge_id)")
        conn.execute("CREATE INDEX idx_interval ON edge_metrics(interval_begin, interval_end)")
        conn.execute("CREATE INDEX idx_speed ON edge_metrics(speed DESC)")
        conn.execute("CREATE INDEX idx_waitingTime ON edge_metrics(waitingTime DESC)")
        
        # trips 인덱스
        conn.execute("CREATE INDEX idx_trips_duration ON trips(duration DESC)")
        conn.execute("CREATE INDEX idx_trips_timeLoss ON trips(timeLoss DESC)")
        conn.execute("CREATE INDEX idx_trips_sim ON trips(simulation_id)")
        conn.execute("CREATE INDEX idx_trips_depart ON trips(depart)")
        conn.execute("CREATE INDEX idx_trips_arrival ON trips(arrival)")


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
