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
                               terrain_aspect: float = 180.0) -> dict:
        """
        Calcula la sombra agregada de un array de paneles.
        Cada panel se proyecta independientemente; se devuelve la unión.
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

        individual_polygons = []
        for lon, lat in panel_positions:
            dx_m = (lon - ref_lon) * meters_per_deg_lon
            dy_m = (lat - ref_lat) * meters_per_deg_lat

            res = self.calculate_shadow_polygon(
                panel_width=panel_width,
                panel_length=panel_length,
                panel_tilt=panel_tilt,
                panel_azimuth=panel_azimuth,
                solar_elevation=solar_elevation,
                solar_azimuth=solar_azimuth,
                clearance_height=clearance_height,
                terrain_slope=terrain_slope,
                terrain_aspect=terrain_aspect
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
