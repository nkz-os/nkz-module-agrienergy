import numpy as np
from shapely.geometry import Polygon
from shapely.affinity import rotate, translate, scale

class ShadowEngine:
    """
    Motor de geometría vectorial 2.5D.
    Proyecta las sombras de los paneles sobre un terreno inclinado.
    """
    
    @staticmethod
    def _rotation_matrix_z(angle_deg):
        theta = np.radians(angle_deg)
        c, s = np.cos(theta), np.sin(theta)
        return np.array([
            [c, -s, 0],
            [s, c, 0],
            [0, 0, 1]
        ])

    @staticmethod
    def _rotation_matrix_x(angle_deg):
        theta = np.radians(angle_deg)
        c, s = np.cos(theta), np.sin(theta)
        return np.array([
            [1, 0, 0],
            [0, c, -s],
            [0, s, c]
        ])

    def calculate_shadow_polygon(self, 
                                 panel_width: float, 
                                 panel_length: float, 
                                 panel_tilt: float, 
                                 panel_azimuth: float, 
                                 solar_elevation: float, 
                                 solar_azimuth: float,
                                 clearance_height: float = 2.0,
                                 terrain_slope: float = 0.0,
                                 terrain_aspect: float = 180.0) -> dict:
        """
        Calcula el polígono de sombra proyectado en un plano 2.5D.
        Devuelve el área y las coordenadas relativas.
        """
        if solar_elevation <= 0:
            return {"area_m2": 0.0, "polygon": []}
            
        # 1. Definir panel como rectángulo horizontal centrado en el origen (Z=1m de altura base por ejemplo)
        # Asumimos eje de rotación en el centro
        w2 = panel_width / 2
        l2 = panel_length / 2
        
        # Vértices locales (X, Y, Z)
        vertices = np.array([
            [-w2, -l2, 0],
            [w2, -l2, 0],
            [w2, l2, 0],
            [-w2, l2, 0]
        ])
        
        # 2. Rotación del panel (Tilt en X, Azimuth en Z)
        # Asumiendo Azimuth 0 = Norte, 90 = Este (estándar). 
        # Cuidado con las convenciones: pvlib suele usar Norte=0. 
        # Aquí rotamos Y hacia abajo (inclinación) y luego rotamos en el plano XY
        R_tilt = self._rotation_matrix_x(panel_tilt)
        # Ajuste de azimut (180 es Sur en pvlib)
        R_az = self._rotation_matrix_z(180 - panel_azimuth) 
        
        vertices_rotated = (R_az @ (R_tilt @ vertices.T)).T
        
        # Añadir altura base al poste geométrico para proyección
        vertices_rotated[:, 2] += clearance_height

        # 3. Vector solar (RAYO DE LUZ DESDE EL SOL AL SUELO)
        # Apuntamos hacia ABAJO (negativo Z)
        el_rad = np.radians(solar_elevation)
        az_rad = np.radians(180 - solar_azimuth) 
        
        # Vector apuntando hacia el sol:
        # sz = sin(el), sy = cos(el)*cos(az), sx = cos(el)*sin(az)
        # Invertimos para obtener el rayo que Cae:
        sz_ray = -np.sin(el_rad)
        sy_ray = -np.cos(el_rad) * np.cos(az_rad)
        sx_ray = -np.cos(el_rad) * np.sin(az_rad)
        
        ray_vector = np.array([sx_ray, sy_ray, sz_ray])
        
        # 4. Proyección sobre terreno 2.5D
        # Si el terreno tiene pendiente, el vector normal Z no es (0,0,1)
        # Normal del terreno:
        slope_rad = np.radians(terrain_slope)
        aspect_rad = np.radians(180 - terrain_aspect)
        
        nx = np.sin(slope_rad) * np.sin(aspect_rad)
        ny = np.sin(slope_rad) * np.cos(aspect_rad)
        nz = np.cos(slope_rad)
        terrain_normal = np.array([nx, ny, nz])
        
        # Proyección de cada vértice al plano del terreno por el vector solar
        projected = []
        for v in vertices_rotated:
            # t = (N·P - N·V) / (N·R) donde P=(0,0,0) origen topográfico, R es el Ray Vector
            dot_nr = np.dot(terrain_normal, ray_vector)
            if dot_nr >= 0:
                continue # El rayo sale del suelo o no lo cruza
                
            t = -np.dot(terrain_normal, v) / dot_nr
            p_proj = v + t * ray_vector
            projected.append(p_proj[:2]) # 2D en el plano topográfico

        if len(projected) < 3:
             return {"area_m2": 0.0, "polygon": []}
             
        # Crear polígono 2D plano (Shapely)
        poly = Polygon(projected).convex_hull
        
        return {
            "area_m2": poly.area,
            "polygon": list(poly.exterior.coords)
        }

    def calculate_array_shadow(self,
                               panel_positions: list,  # [(lon, lat), ...] from MultiPoint
                               panel_width: float,
                               panel_length: float,
                               panel_tilt: float,
                               panel_azimuth: float,
                               solar_elevation: float,
                               solar_azimuth: float,
                               clearance_height: float = 2.0,
                               terrain_slope: float = 0.0,
                               terrain_aspect: float = 180.0,
                               elevations: list | None = None) -> dict:
        """
        Calcula la sombra agregada de un array de paneles.
        Cada panel se proyecta independientemente; se devuelve la unión.

        Si se proporciona `elevations` (una elevación en metros por cada posición),
        se calcula la pendiente local del terreno en cada panel usando su vecino
        más cercano, en lugar de usar un plano inclinado global.
        """
        from shapely.ops import unary_union
        from shapely.affinity import translate as shapely_translate

        if not panel_positions:
            return {"area_m2": 0.0, "polygon": [], "individual_polygons": []}

        ref_lon = panel_positions[0][0]
        ref_lat = panel_positions[0][1]
        lat_rad = np.radians(ref_lat)
        meters_per_deg_lat = 111320.0
        meters_per_deg_lon = 111320.0 * np.cos(lat_rad)

        # Precompute local terrain per panel from real elevations
        n = len(panel_positions)
        has_elevations = elevations is not None and len(elevations) == n

        individual_polygons = []
        for idx, (lon, lat) in enumerate(panel_positions):
            dx_m = (lon - ref_lon) * meters_per_deg_lon
            dy_m = (lat - ref_lat) * meters_per_deg_lat

            # Local terrain: use real elevation data if available
            local_slope = terrain_slope
            local_aspect = terrain_aspect
            if has_elevations and elevations is not None:
                local_slope, local_aspect = self._local_terrain(
                    idx, panel_positions, elevations,
                    meters_per_deg_lon, meters_per_deg_lat,
                    fallback_slope=terrain_slope, fallback_aspect=terrain_aspect
                )

            res = self.calculate_shadow_polygon(
                panel_width=panel_width,
                panel_length=panel_length,
                panel_tilt=panel_tilt,
                panel_azimuth=panel_azimuth,
                solar_elevation=solar_elevation,
                solar_azimuth=solar_azimuth,
                clearance_height=clearance_height,
                terrain_slope=local_slope,
                terrain_aspect=local_aspect
            )

            if res["polygon"] and len(res["polygon"]) >= 3:
                poly = Polygon(res["polygon"])
                poly_translated = shapely_translate(poly, xoff=dx_m, yoff=dy_m)
                individual_polygons.append(poly_translated)

        if not individual_polygons:
            return {"area_m2": 0.0, "polygon": [], "individual_polygons": []}

        merged = unary_union(individual_polygons)

        return {
            "area_m2": merged.area,
            "polygon": list(merged.exterior.coords) if hasattr(merged, 'exterior') else [],
            "individual_polygons": [list(p.exterior.coords) for p in individual_polygons]
        }

    @staticmethod
    def _local_terrain(
        idx: int,
        positions: list,  # [(lon, lat), ...]
        elevations: list,  # elevation in meters per position
        m_per_deg_lon: float,
        m_per_deg_lat: float,
        fallback_slope: float = 0.0,
        fallback_aspect: float = 180.0,
    ) -> tuple:
        """
        Compute local terrain slope/aspect at position idx using its nearest neighbor.
        Falls back to global values for isolated panels.
        """
        n = len(positions)
        if n < 2:
            return fallback_slope, fallback_aspect

        my_lon, my_lat = positions[idx]
        my_elev = elevations[idx]

        # Find nearest neighbor
        best_dist = float("inf")
        best_dx = 0.0
        best_dy = 0.0
        best_de = 0.0
        for j in range(n):
            if j == idx:
                continue
            dlon = (positions[j][0] - my_lon) * m_per_deg_lon
            dlat = (positions[j][1] - my_lat) * m_per_deg_lat
            dist = np.sqrt(dlon * dlon + dlat * dlat)
            if dist < best_dist and dist > 0.001:  # avoid self
                best_dist = dist
                best_dx = dlon
                best_dy = dlat
                best_de = elevations[j] - my_elev

        if best_dist == float("inf") or best_dist < 0.001:
            return fallback_slope, fallback_aspect

        # Slope = angle of elevation gradient (degrees)
        local_slope_rad = np.arctan2(abs(best_de), best_dist)
        local_slope = float(np.degrees(local_slope_rad))

        # Aspect = direction of steepest descent (0=North, 90=East, 180=South)
        # bearing from current position toward neighbor
        bearing_rad = np.arctan2(best_dx, best_dy)  # dx→East, dy→North
        bearing_deg = float(np.degrees(bearing_rad))
        if bearing_deg < 0:
            bearing_deg += 360.0

        # Aspect is the direction the slope FACES (downhill)
        if best_de > 0:
            local_aspect = bearing_deg  # neighbor is higher → downhill is opposite
        else:
            local_aspect = (bearing_deg + 180.0) % 360.0

        return local_slope, local_aspect
