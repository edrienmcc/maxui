# -*- coding: utf-8 -*-
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import mysql.connector
from datetime import datetime
from urllib.parse import urlparse
import base64
import json

def obtener_slug(url):
    """Extrae el slug de una URL de jkanime"""
    path = urlparse(url).path
    # Eliminar barras y obtener el último segmento de la URL
    slug = path.strip('/').split('/')[-1]
    return slug

def existe_anime_en_bd(cursor, slug):
    """Verifica si el anime ya existe en la base de datos"""
    try:
        print(f"[DEBUG] Verificando si el slug '{slug}' existe en la base de datos")
        query = "SELECT COUNT(*) FROM animes WHERE slug = %s"
        cursor.execute(query, (slug,))
        count = cursor.fetchone()[0]
        print(f"[DEBUG] Resultado de la consulta: {count} coincidencias")
        return count > 0
    except Exception as e:
        print(f"[ERROR] Error al verificar anime en la base de datos: {e}")
        return False  # En caso de error, asumimos que no existe para intentar agregarlo

def extraer_detalle_anime(driver, url, slug):
    """Extrae los detalles de un anime desde su página individual"""
    print(f"[DEBUG] Navegando a la URL del anime: {url}")
    driver.get(url)
    print(f"[DEBUG] Esperando 5 segundos para que cargue la página...")
    time.sleep(5)  # Aumentado de 3 a 5 segundos para asegurar carga completa
    
    try:
        # Extraer título
        titulo_elemento = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".anime__details__title h3"))
        )
        title = titulo_elemento.text
        
        # Extraer descripción
        descripcion_elemento = driver.find_element(By.CSS_SELECTOR, "p.tab.sinopsis")
        description = descripcion_elemento.text
        
        # Extraer URL de la imagen
        poster_elemento = driver.find_element(By.CSS_SELECTOR, ".anime__details__pic.set-bg")
        poster = poster_elemento.get_attribute("data-setbg")
        
        # Extraer ID del trailer de YouTube (si existe)
        trailer_id = None
        try:
            trailer_elemento = driver.find_element(By.CSS_SELECTOR, "div.animeTrailer")
            if trailer_elemento:
                trailer_id = trailer_elemento.get_attribute("data-yt")
                print(f"[DEBUG] ID del trailer encontrado: {trailer_id}")
        except Exception as e:
            print(f"[DEBUG] No se encontró trailer o error al extraerlo: {e}")
            trailer_id = None
        
        # Extraer número total de episodios (si existe)
        total_episodios = None
        try:
            # Buscar todos los enlaces de números
            numeros_elementos = driver.find_elements(By.CSS_SELECTOR, "a.numbers")
            if numeros_elementos and len(numeros_elementos) > 0:
                # Obtener el último elemento
                ultimo_elemento = numeros_elementos[-1]
                # Extraer el texto (por ejemplo: "157 - 167")
                texto = ultimo_elemento.text
                # Dividir por "-" y obtener el último número
                partes = texto.split("-")
                if len(partes) > 1:
                    # Obtener el último número y eliminar espacios
                    ultimo_numero = partes[1].strip()
                    total_episodios = ultimo_numero
                    print(f"[DEBUG] Total de episodios encontrado: {total_episodios}")
                else:
                    # Si no hay guion, usar el número completo
                    total_episodios = texto.strip()
                    print(f"[DEBUG] Total de episodios encontrado (sin guion): {total_episodios}")
        except Exception as e:
            print(f"[DEBUG] No se encontró información de episodios o error al extraerla: {e}")
            total_episodios = None
        
        return {
            'slug': slug,
            'title': title,
            'description': description,
            'poster': poster,
            'trailer_id': trailer_id,
            'total_episodios': total_episodios
        }
    except Exception as e:
        print(f"[ERROR] Error al extraer detalles del anime {url}: {e}")
        return None

def decodificar_base64(texto_codificado):
    """Decodifica un texto en base64"""
    try:
        # Decodificar el texto de base64
        texto_bytes = base64.b64decode(texto_codificado)
        # Convertir bytes a string
        texto_decodificado = texto_bytes.decode('utf-8')
        # Eliminar posibles saltos de línea al final
        texto_decodificado = texto_decodificado.strip()
        return texto_decodificado
    except Exception as e:
        print(f"[ERROR] Error al decodificar base64: {e}")
        return None

def es_url_valida(url):
    """Verifica si una URL es válida y no está en la lista de URLs a ignorar."""
    # Lista de dominios para ignorar
    dominios_ignorar = [
        "c1.jkplayers.com",
        "disqus.com",
        "liadm.com",
        "googleapis.com",
        "gstatic.com",
        "google.com"
    ]
    
    # Verificar si la URL contiene alguno de los dominios a ignorar
    for dominio in dominios_ignorar:
        if dominio in url:
            print(f"[FILTRO] URL ignorada (dominio en lista negra): {url}")
            return False
    
    # Verificar si la URL es válida: debe comenzar con http:// o https:// o /
    if (url.startswith(("http://", "https://", "/")) and 
        "','src=" not in url and 
        ".js" not in url and 
        ".css" not in url):
        # Verificar que no termine con extensiones no deseadas
        if not url.endswith((".js", ".css", ".png", ".jpg", ".gif")):
            return True
    
    print(f"[FILTRO] URL ignorada (no cumple criterios): {url}")
    return False

def extraer_datos_episodio(driver, url_base, numero_episodio, episode_id):
    """Extrae los datos de un episodio específico"""
    try:
        # Construir URL del episodio
        url_episodio = f"{url_base}/{numero_episodio}/"
        print(f"[DEBUG] Navegando a episodio: {url_episodio}")
        print(f"[🔗 URL] EPISODIO {numero_episodio}: {url_episodio}")  # URLs destacadas para visualizar
        
        # Navegar a la página del episodio
        driver.get(url_episodio)
        time.sleep(3)  # Esperar a que cargue la página
        
        # Extraer imagen del episodio
        imagen_episodio = None
        try:
            meta_imagen = driver.find_element(By.CSS_SELECTOR, "meta[property='og:image']")
            if meta_imagen:
                imagen_episodio = meta_imagen.get_attribute("content")
                print(f"[DEBUG] Imagen del episodio encontrada: {imagen_episodio}")
        except Exception as e:
            print(f"[DEBUG] No se encontró imagen del episodio: {e}")
            
            # Intento alternativo: buscar la imagen en otros elementos
            try:
                # Buscar imagen en otros lugares posibles
                posibles_elementos = [
                    "div.anime__details__pic.set-bg",
                    "div.capitulovideo > img",
                    "div.vimg > img",
                    "video > source"
                ]
                
                for selector in posibles_elementos:
                    try:
                        elemento = driver.find_element(By.CSS_SELECTOR, selector)
                        if selector.endswith("img"):
                            imagen_episodio = elemento.get_attribute("src")
                        elif selector.endswith("source"):
                            imagen_episodio = elemento.get_attribute("src")
                        else:
                            imagen_episodio = elemento.get_attribute("data-setbg")
                        
                        if imagen_episodio:
                            print(f"[DEBUG] Imagen alternativa encontrada: {imagen_episodio}")
                            break
                    except:
                        continue
            except Exception as alt_err:
                print(f"[DEBUG] Error en búsqueda alternativa de imagen: {alt_err}")
        
        # Inicializar todos los reproductores
        todos_reproductores = []
        
        # 1. Extraer reproductores de video[] array - PRIORIDAD 1
        reproductores_video_array = []
        try:
            # Buscar reproductores en scripts con formato video[X]
            scripts = driver.find_elements(By.TAG_NAME, "script")
            for script in scripts:
                script_text = script.get_attribute("innerHTML")
                
                # Buscar patrones como video[1], video[2], video[3], etc.
                video_patterns = re.findall(r'video\[(\d+)\]\s*=\s*\'<iframe[^>]*src="([^"]+)"', script_text)
                
                for i, src in video_patterns:
                    # Procesar la URL del reproductor
                    if src.startswith("/"):
                        # Si es una ruta relativa, convertirla a absoluta
                        if src.startswith("/jk.php"):
                            # Reproductor especial /jk.php
                            url_completa = f"https://jkanime.org{src}"
                            print(f"[DEBUG] Reproductor JK encontrado: {url_completa}")
                            print(f"[🔗 REPRODUCTOR-JK] EP{numero_episodio} - Video[{i}]: {url_completa}")
                            
                            domain = "jkanime.org"
                            reproductores_video_array.append({
                                "url": url_completa,
                                "tipo": "jk",
                                "nombre": f"Server JK {i}",
                                "domain": domain,
                                "indice": int(i)  # Guardar el índice para ordenar después
                            })
                        elif src.startswith("/um.php") or src.startswith("/umv.php"):
                            # Reproductor um.php o umv.php
                            url_completa = f"https://jkanime.org{src}"
                            print(f"[DEBUG] Reproductor UM/UMV encontrado: {url_completa}")
                            print(f"[🔗 REPRODUCTOR-UM] EP{numero_episodio} - Video[{i}]: {url_completa}")
                            
                            domain = "jkanime.org"
                            reproductores_video_array.append({
                                "url": url_completa,
                                "tipo": "um",
                                "nombre": f"Server {i}",
                                "domain": domain,
                                "indice": int(i)  # Guardar el índice para ordenar después
                            })
                    else:
                        # URL completa externa
                        if es_url_valida(src):
                            print(f"[DEBUG] Reproductor externo: {src}")
                            print(f"[🔗 REPRODUCTOR-EXT] EP{numero_episodio} - Video[{i}]: {src}")
                            
                            domain = f"{urlparse(src).scheme}://{urlparse(src).netloc}"
                            reproductores_video_array.append({
                                "url": src,
                                "tipo": "externo",
                                "nombre": f"Server {i}",
                                "domain": domain,
                                "indice": int(i)  # Guardar el índice para ordenar después
                            })
            
            # Ordenar por índice para mantener el mismo orden que en la página
            reproductores_video_array.sort(key=lambda x: x["indice"])
            
            print(f"[DEBUG] Total de reproductores video[] encontrados: {len(reproductores_video_array)}")
            
        except Exception as e:
            print(f"[ERROR] Error al extraer reproductores de video[]: {e}")
        
        # 2. Extraer servidores codificados en base64 - PRIORIDAD 2
        servidores_b64 = []
        try:
            # Buscar la parte del script que contiene los servidores en base64
            scripts = driver.find_elements(By.TAG_NAME, "script")
            for script in scripts:
                script_text = script.get_attribute("innerHTML")
                if "var servers = [" in script_text:
                    print("[DEBUG] Encontrados servidores en base64")
                    
                    # Extraer el array JSON de servidores
                    try:
                        # Encontrar el inicio del array JSON
                        inicio = script_text.find("var servers = ") + len("var servers = ")
                        fin = script_text.find("];", inicio) + 1
                        if inicio > 0 and fin > 0:
                            json_texto = script_text[inicio:fin]
                            # Parsear el JSON
                            servidores = json.loads(json_texto)
                            print(f"[DEBUG] Se encontraron {len(servidores)} servidores en base64")
                            
                            # Procesar cada servidor
                            for servidor in servidores:
                                remote_b64 = servidor.get("remote")
                                server_name = servidor.get("server")
                                
                                # Decodificar la URL para todos los servidores, incluido Mediafire
                                if remote_b64:
                                    url_decodificada = decodificar_base64(remote_b64)
                                    if url_decodificada and es_url_valida(url_decodificada):
                                        print(f"[DEBUG] Servidor {server_name}: {url_decodificada}")
                                        print(f"[🔗 REPRODUCTOR-B64] EP{numero_episodio} - {server_name}: {url_decodificada}")
                                        
                                        # Guardar el dominio base para usar como header
                                        parsed_url = urlparse(url_decodificada)
                                        base_domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
                                        
                                        servidores_b64.append({
                                            "url": url_decodificada,
                                            "tipo": "base64",
                                            "nombre": server_name,
                                            "domain": base_domain
                                        })
                    except json.JSONDecodeError as je:
                        print(f"[ERROR] Error al parsear JSON de servidores: {je}")
                    except Exception as ex:
                        print(f"[ERROR] Error general al procesar servidores en base64: {ex}")
        except Exception as e:
            print(f"[ERROR] Error al buscar servidores en base64: {e}")
        
        # Ordenar servidores según los requerimientos
        servidores_ordenados = []
        
        # 1. Primero agregar todos los reproductores de video[] (JK, UM, UMV, etc.)
        servidores_ordenados.extend(reproductores_video_array)
        
        # 2. Luego agregar servidores específicos en base64 en el orden solicitado 
        servidores_orden = ["Streamwish", "Vidhide", "Mp4upload", "VOE"]
        
        for nombre_servidor in servidores_orden:
            for servidor in servidores_b64:
                if servidor["nombre"] == nombre_servidor:
                    servidores_ordenados.append(servidor)
                    # Marcar como procesado para no duplicar
                    servidores_b64 = [s for s in servidores_b64 if s != servidor]
        
        # 3. Si hay pocos reproductores, buscar alternativas
        if len(servidores_ordenados) < 2:
            try:
                # Método alternativo: Buscar elementos iframe directamente
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    src = iframe.get_attribute("src")
                    if src and es_url_valida(src):
                        # Verificar que no esté ya incluido
                        if not any(r["url"] == src for r in servidores_ordenados):
                            print(f"[DEBUG] Reproductor encontrado en iframe: {src}")
                            print(f"[🔗 REPRODUCTOR-IFRAME] EP{numero_episodio}: {src}")
                            
                            domain = f"{urlparse(src).scheme}://{urlparse(src).netloc}"
                            servidores_ordenados.append({
                                "url": src,
                                "tipo": "iframe",
                                "nombre": f"Servidor {len(servidores_ordenados) + 1}",
                                "domain": domain
                            })
            except Exception as e:
                print(f"[ERROR] Error al buscar iframes: {e}")
        
        # Si no se encontraron reproductores, crear uno predeterminado
        if not servidores_ordenados:
            print("[DEBUG] No se encontraron reproductores. Creando URL predeterminada")
            reproductor_default = f"https://jkanime.org/um.php?e=default&t={numero_episodio}"
            print(f"[🔗 REPRODUCTOR-DEFAULT] EP{numero_episodio}: {reproductor_default}")
            servidores_ordenados.append({
                "url": reproductor_default,
                "tipo": "default",
                "nombre": "Servidor 1",
                "domain": "jkanime.org"
            })
        
        print(f"[DEBUG] Total de reproductores finales: {len(servidores_ordenados)}")
        
        return {
            "imagen": imagen_episodio,
            "reproductores": servidores_ordenados
        }
    except Exception as e:
        print(f"[ERROR] Error al extraer datos del episodio {numero_episodio}: {e}")
        return {
            "imagen": None,
            "reproductores": []
        }

def insertar_videos_episodio(conn, cursor, episodio_id, datos_episodio):
    """Inserta los videos de un episodio en la base de datos"""
    try:
        # Si hay imagen del episodio, actualizar el episodio
        if datos_episodio and datos_episodio.get('imagen'):
            print(f"[DEBUG] Actualizando imagen del episodio ID {episodio_id}: {datos_episodio['imagen']}")
            query_update = """
            UPDATE anime_episodes 
            SET still_path = %s, still_path_tv = %s 
            WHERE id = %s
            """
            values_update = (
                datos_episodio['imagen'],
                datos_episodio['imagen'],
                episodio_id
            )
            cursor.execute(query_update, values_update)
            conn.commit()
            print(f"[DEBUG] Actualizada imagen del episodio ID {episodio_id}")
        
        # Verificar si hay reproductores
        if not datos_episodio or 'reproductores' not in datos_episodio or not datos_episodio['reproductores']:
            print(f"[DEBUG] No hay reproductores para el episodio ID {episodio_id}")
            return False
        
        # Insertar cada reproductor
        for i, reproductor in enumerate(datos_episodio['reproductores']):
            reproductor_url = reproductor["url"]
            tipo = reproductor.get("tipo", "principal")
            domain = reproductor.get("domain", "https://jkanime.org")
            
            # Asignar nombre del servidor según el índice o el tipo
            if "nombre" in reproductor:
                server = reproductor["nombre"]
            elif i == 0:
                server = "1080P"
            elif i == 1:
                server = "720P"
            else:
                server = f"Servidor {i+1}"
            
            print(f"[DEBUG] Insertando reproductor {server} para episodio ID {episodio_id}: {reproductor_url}")
            print(f"[DEBUG] Header (dominio): {domain}")
            print(f"[✅ INSERTADO] Reproductor {server} para episodio ID {episodio_id}")
            
            # Consulta SQL que incluye todos los campos requeridos
            query = """
            INSERT INTO anime_videos 
            (anime_episode_id, server, header, useragent, link, lang, video_name, embed, 
            youtubelink, hls, supported_hosts, drm, drmuuid, drmlicenceuri, status, created_at, updated_at) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            values = (
                episodio_id,                # anime_episode_id
                server,                     # server
                domain,                     # header (usando el dominio base)
                None,                       # useragent
                reproductor_url,            # link
                "Spanish",                  # lang
                None,                       # video_name
                0,                          # embed (0 para todos según el ejemplo)
                0,                          # youtubelink
                0,                          # hls (0 para primer reproductor, 1 para el segundo)
                1,                          # supported_hosts
                0,                          # drm
                None,                       # drmuuid
                None,                       # drmlicenceuri
                1,                          # status
                now,                        # created_at
                now                         # updated_at
            )
            
            try:
                cursor.execute(query, values)
                # Verificar que la inserción tuvo éxito
                lastid = cursor.lastrowid
                print(f"[DEBUG] Reproductor insertado con ID: {lastid}")
            except Exception as e:
                print(f"[ERROR] Error al insertar reproductor {i+1}: {e}")
                print(f"[ERROR] Consulta: {query}")
                print(f"[ERROR] Valores: {values}")
        
        conn.commit()
        print(f"[DEBUG] Insertados {len(datos_episodio['reproductores'])} reproductores para el episodio ID {episodio_id}")
        return True
    except Exception as e:
        print(f"[ERROR] Error al insertar videos para el episodio {episodio_id}: {e}")
        conn.rollback()
        return False

def insertar_temporadas_episodios(conn, cursor, anime_id, total_episodios, slug):
    """Inserta las temporadas y episodios para un anime"""
    try:
        if not total_episodios or not total_episodios.isdigit():
            print(f"[DEBUG] No hay total de episodios o no es un número válido: {total_episodios}")
            return False
        
        total_eps = int(total_episodios)
        print(f"[DEBUG] Creando temporadas y episodios para anime ID {anime_id}, total episodios: {total_eps}")
        
        # Calcular número de temporadas (cada 12 episodios)
        num_temporadas = (total_eps + 11) // 12  # Redondeo hacia arriba
        print(f"[DEBUG] Se crearán {num_temporadas} temporadas")
        
        # Construir la URL base para los episodios
        url_base = f"https://jkanime.org/{slug}"
        print(f"[🔗 URL BASE] ANIME: {url_base}")  # URL destacada
        
        for temp_num in range(1, num_temporadas + 1):
            # Insertar temporada
            query_temporada = """
            INSERT INTO anime_seasons 
            (anime_id, season_number, name, created_at, updated_at) 
            VALUES (%s, %s, %s, %s, %s)
            """
            
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            values_temporada = (
                anime_id,                        # anime_id
                temp_num,                        # season_number
                f"Temporada {temp_num}",         # name
                now,                             # created_at
                now                              # updated_at
            )
            
            print(f"[DEBUG] Insertando temporada {temp_num}")
            cursor.execute(query_temporada, values_temporada)
            conn.commit()
            
            # Obtener el ID de la temporada recién insertada
            temporada_id = cursor.lastrowid
            print(f"[DEBUG] Temporada insertada con ID: {temporada_id}")
            print(f"[✅ INSERTADO] Temporada {temp_num} con ID: {temporada_id}")  # Confirmación
            
            # Calcular episodios para esta temporada
            primer_episodio = (temp_num - 1) * 12 + 1
            ultimo_episodio = min(temp_num * 12, total_eps)
            
            print(f"[DEBUG] Insertando episodios del {primer_episodio} al {ultimo_episodio} para temporada {temp_num}")
            
            # Insertar episodios
            episodios_ids = {}  # Diccionario para guardar {num_episodio: episodio_id}
            
            for ep_num in range(primer_episodio, ultimo_episodio + 1):
                query_episodio = """
                INSERT INTO anime_episodes 
                (anime_season_id, episode_number, name, enable_stream, enable_media_download, 
                still_path, still_path_tv, created_at, updated_at) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                # Usar la imagen del anime como still_path
                query_imagen = "SELECT poster_path FROM animes WHERE id = %s"
                cursor.execute(query_imagen, (anime_id,))
                imagen_result = cursor.fetchone()
                imagen = imagen_result[0] if imagen_result else None
                
                values_episodio = (
                    temporada_id,                # anime_season_id
                    ep_num - primer_episodio + 1,# episode_number (relativo a la temporada)
                    f"Capitulo {ep_num}",        # name
                    1,                           # enable_stream
                    1,                           # enable_media_download
                    imagen,                      # still_path
                    imagen,                      # still_path_tv
                    now,                         # created_at
                    now                          # updated_at
                )
                
                cursor.execute(query_episodio, values_episodio)
                conn.commit()
                
                # Guardar el ID del episodio recién insertado
                episodio_id = cursor.lastrowid
                episodios_ids[ep_num] = episodio_id
                print(f"[✅ INSERTADO] Episodio {ep_num} con ID: {episodio_id}")  # Confirmación
                
                # Extraer datos del episodio (imagen y reproductores)
                datos_episodio = extraer_datos_episodio(driver, url_base, ep_num, episodio_id)
                
                # Insertar videos del episodio
                if datos_episodio:
                    insertar_videos_episodio(conn, cursor, episodio_id, datos_episodio)
                
                # Esperar un tiempo entre cada episodio para no sobrecargar el servidor
                print(f"[DEBUG] Esperando 2 segundos antes de procesar el siguiente episodio...")
                time.sleep(2)
            
            print(f"[DEBUG] Episodios insertados correctamente para temporada {temp_num}")
        
        return True
    except Exception as e:
        print(f"[ERROR] Error al insertar temporadas y episodios: {e}")
        conn.rollback()
        return False

def insertar_anime_en_bd(conn, cursor, datos_anime):
    """Inserta un nuevo anime en la base de datos"""
    try:
        # Imprimir los datos que se van a insertar para depuración
        print("[DEBUG] Datos a insertar en la BD:")
        print(f"  - Título: {datos_anime['title']}")
        print(f"  - Descripción: {datos_anime['description'][:30]}...")
        print(f"  - ID Trailer: {datos_anime.get('trailer_id', 'NO HAY')}")
        
        query = """
        INSERT INTO animes (
            name, original_name, slug, overview, poster_path, backdrop_path_tv, 
            backdrop_path, is_anime, active, created_at, updated_at, preview_path
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Obtener el número de episodios para ponerlo en el título si está disponible
        nombre_con_episodios = datos_anime['title']
        if datos_anime.get('total_episodios'):
            nombre_con_episodios = f"{datos_anime['title']} [{datos_anime.get('total_episodios')} Eps]"
        
        # Asegurarse de que el trailer_id no sea None
        trailer_id = datos_anime.get('trailer_id', '')
        if trailer_id is None:
            trailer_id = ''
            
        print(f"[DEBUG] ID del trailer que se va a guardar: '{trailer_id}'")
        
        values = (
            datos_anime['title'],                # name (con número de episodios)
            datos_anime['title'],                # original_name
            datos_anime['slug'],                 # slug
            datos_anime['description'],          # overview
            datos_anime['poster'],               # poster_path
            datos_anime['poster'],               # backdrop_path_tv
            datos_anime['poster'],               # backdrop_path
            1,                                   # is_anime
            1,                                   # active
            now,                                 # created_at
            now,                                 # updated_at
            trailer_id                           # preview_path (ID del trailer de YouTube)
        )
        
        print(f"[DEBUG] Ejecutando insert en la base de datos para '{datos_anime['title']}'")
        cursor.execute(query, values)
        
        # Verificar que la inserción tuvo éxito
        lastid = cursor.lastrowid
        
        # Consultar el registro recién insertado para verificar
        verify_query = "SELECT preview_path FROM animes WHERE id = %s"
        cursor.execute(verify_query, (lastid,))
        result = cursor.fetchone()
        
        if result:
            print(f"[DEBUG] Verificación: preview_path guardado = '{result[0]}'")
        
        conn.commit()
        print(f"[DEBUG] Anime '{datos_anime['title']}' insertado correctamente con ID: {lastid}")
        print(f"[✅ INSERTADO] ANIME: {datos_anime['title']} (ID: {lastid}, Slug: {datos_anime['slug']})")  # Confirmación
        
        # Si tiene total de episodios, insertar temporadas y episodios
        if datos_anime.get('total_episodios'):
            print(f"[DEBUG] Creando temporadas y episodios para anime ID {lastid}")
            insertar_temporadas_episodios(conn, cursor, lastid, datos_anime.get('total_episodios'), datos_anime['slug'])
        
        return True
    except Exception as e:
        print(f"[ERROR] Error al insertar anime en la base de datos: {e}")
        conn.rollback()  # Hacer rollback en caso de error
        return False

def insertar_anime_por_slug(slug):
    """Inserta un anime específico por su slug"""
    print(f"[INFO] Iniciando proceso para insertar el anime con slug: {slug}")
    
    # Configurar la conexión a la base de datos
    conn = None
    cursor = None
    try:
        print("[DEBUG] Intentando conectar a la base de datos...")
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="aruma",  # Cambiar por el nombre real de tu base de datos
            connect_timeout=60  # Aumentar timeout de conexión
        )
        cursor = conn.cursor()
        print("[DEBUG] Conexión a la base de datos establecida correctamente")
        
        # Verificar si el anime ya existe en la base de datos
        if existe_anime_en_bd(cursor, slug):
            print(f"[AVISO] El anime con slug '{slug}' ya existe en la base de datos.")
            return False
        
        # Configurar opciones de Chrome
        chrome_options = Options()
        # Se quita el modo headless para que el navegador sea visible
        # chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        # Inicializar el navegador Chrome
        global driver
        driver = webdriver.Chrome(options=chrome_options)
        
        # URL del anime
        url = f"https://jkanime.org/{slug}"
        
        # Extraer detalles y agregar a la base de datos
        print(f"[INFO] Extrayendo detalles del anime: {url}")
        datos_anime = extraer_detalle_anime(driver, url, slug)
        
        if datos_anime:
            print(f"[INFO] Datos extraídos:")
            print(f"  - Título: {datos_anime.get('title')}")
            print(f"  - Descripción: {datos_anime.get('description')[:50]}...")
            print(f"  - ID Trailer: {datos_anime.get('trailer_id')}")
            print(f"  - Total Episodios: {datos_anime.get('total_episodios')}")
            
            # Insertar en la base de datos
            insertar_anime_en_bd(conn, cursor, datos_anime)
            print(f"[INFO] Proceso completado para el anime '{datos_anime['title']}'")
            return True
        else:
            print(f"[ERROR] No se pudieron extraer datos del anime con slug: {slug}")
            return False
        
    except Exception as e:
        print(f"[ERROR] Error al procesar el anime: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        # Cerrar conexiones
        print("[DEBUG] Finalizando proceso, cerrando conexiones...")
        if cursor:
            try:
                cursor.close()
                print("[DEBUG] Cursor cerrado correctamente")
            except Exception as e:
                print(f"[ERROR] Error al cerrar cursor: {e}")
        
        if conn:
            try:
                conn.close()
                print("[DEBUG] Conexión a la base de datos cerrada correctamente")
            except Exception as e:
                print(f"[ERROR] Error al cerrar conexión a la base de datos: {e}")
        
        try:
            driver.quit()
            print("[DEBUG] Navegador cerrado correctamente")
        except Exception as e:
            print(f"[ERROR] Error al cerrar el navegador: {e}")
            
        print("[DEBUG] Proceso completado")

def extraer_animes_jkanime():
    print("[DEBUG] Iniciando proceso de extracción de animes")
    # Configurar la conexión a la base de datos
    conn = None
    cursor = None
    try:
        print("[DEBUG] Intentando conectar a la base de datos...")
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="aruma",  # Cambiar por el nombre real de tu base de datos
            connect_timeout=60    # Aumentar timeout de conexión
        )
        cursor = conn.cursor()
        print("[DEBUG] Conexión a la base de datos establecida correctamente")
    except Exception as e:
        print(f"[ERROR] Error al conectar a la base de datos: {e}")
        return
    
    # Configurar opciones de Chrome
    chrome_options = Options()
    # Se quita el modo headless para que el navegador sea visible
    # chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # Inicializar el navegador Chrome
    global driver
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        # Navegar a la página
        print("[DEBUG] Iniciando navegación a la página de directorio de JKAnime...")
        driver.get("https://jkanime.org/directorio/")
        
        # Esperar 5 segundos como se solicitó
        print("[DEBUG] Esperando 5 segundos iniciales...")
        time.sleep(5)
        
        # Extraer información de los animes
        print("[DEBUG] Extrayendo información de animes...")
        
        # Variables para seguimiento
        animes_agregados = 0
        animes_existentes = 0
        pagina_actual = 1
        
        while True:
            print(f"[DEBUG] Procesando página {pagina_actual}")
            
            # Esperar a que los elementos estén disponibles
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".row.mode1 .dir1"))
            )
            
            # Obtener los elementos actuales
            animes = driver.find_elements(By.CSS_SELECTOR, ".row.mode1 .dir1")
            print(f"[DEBUG] Se encontraron {len(animes)} animes en la página {pagina_actual}")
            
            for index, anime in enumerate(animes):
                try:
                    print(f"\n[DEBUG] Procesando anime {index+1} de {len(animes)} en página {pagina_actual}")
                    
                    # Volver a recuperar el elemento para evitar stale reference
                    animes_actualizados = driver.find_elements(By.CSS_SELECTOR, ".row.mode1 .dir1")
                    if index < len(animes_actualizados):
                        anime_actual = animes_actualizados[index]
                    else:
                        print("[ERROR] Índice de anime fuera de rango después de actualizar la lista")
                        continue
                    
                    # Extraer URL
                    try:
                        url_elemento = anime_actual.find_element(By.CSS_SELECTOR, "h5.card-title a")
                        url = url_elemento.get_attribute("href")
                    except Exception as e:
                        print(f"[ERROR] No se pudo extraer la URL: {e}")
                        continue
                    
                    # Obtener el slug de la URL
                    slug = obtener_slug(url)
                    print(f"[DEBUG] URL: {url}")
                    print(f"[🔗 URL] ANIME: {url}")  # URL destacada
                    print(f"[DEBUG] Slug: {slug}")
                    
                    # Verificar si el anime ya existe en la base de datos
                    if existe_anime_en_bd(cursor, slug):
                        print(f"[DEBUG] El anime con slug '{slug}' ya existe en la base de datos. Saltando...")
                        animes_existentes += 1
                        # Esperar 2 segundos antes de pasar al siguiente anime
                        print("[DEBUG] Esperando 2 segundos antes de pasar al siguiente anime...")
                        time.sleep(2)
                        continue
                    
                    # Si no existe, extraer detalles y agregar a la base de datos
                    print(f"[DEBUG] Extrayendo detalles del anime: {url}")
                    datos_anime = extraer_detalle_anime(driver, url, slug)
                    
                    if datos_anime:
                        print(f"[DEBUG] Datos extraídos:")
                        print(f"  - Título: {datos_anime.get('title')}")
                        print(f"  - Descripción: {datos_anime.get('description')[:50]}...")
                        print(f"  - ID Trailer: {datos_anime.get('trailer_id')}")
                        print(f"  - Total Episodios: {datos_anime.get('total_episodios')}")
                        
                        insertar_anime_en_bd(conn, cursor, datos_anime)
                        animes_agregados += 1
                        print(f"[DEBUG] Anime agregado correctamente. Esperando 10 segundos antes del siguiente anime...")
                        time.sleep(10)  # Esperar 10 segundos entre cada inserción de anime
                    
                    # Volver a la página del directorio
                    print("[DEBUG] Volviendo a la página del directorio...")
                    driver.get(f"https://jkanime.org/directorio/?p={pagina_actual}")
                    time.sleep(5)  # Esperar a que cargue la página
                    
                    print("-" * 50)
                    
                except Exception as e:
                    print(f"[ERROR] Error al procesar un anime: {e}")
                    # Intentar volver a la página del directorio en caso de error
                    try:
                        driver.get(f"https://jkanime.org/directorio/?p={pagina_actual}")
                        time.sleep(5)
                    except:
                        pass
            
            # Intentar ir a la siguiente página
            try:
                # Verificar si hay botón de siguiente página
                siguiente_botones = driver.find_elements(By.CSS_SELECTOR, "a.next.page-numbers")
                if len(siguiente_botones) > 0:
                    print(f"[DEBUG] Pasando a la página {pagina_actual + 1}")
                    siguiente_botones[0].click()
                    pagina_actual += 1
                    time.sleep(5)  # Esperar a que cargue la siguiente página
                else:
                    print("[DEBUG] No hay más páginas. Terminando.")
                    break
            except Exception as e:
                print(f"[ERROR] Error al intentar pasar a la siguiente página: {e}")
                break
        
        print(f"[DEBUG] Proceso completado.")
        print(f"[DEBUG] Animes agregados: {animes_agregados}")
        print(f"[DEBUG] Animes ya existentes: {animes_existentes}")
        
    except Exception as e:
        print(f"[ERROR] Error general: {e}")
    finally:
        # Cerrar conexiones
        print("[DEBUG] Finalizando proceso, cerrando conexiones...")
        if cursor:
            try:
                cursor.close()
                print("[DEBUG] Cursor cerrado correctamente")
            except Exception as e:
                print(f"[ERROR] Error al cerrar cursor: {e}")
        
        if conn:
            try:
                conn.close()
                print("[DEBUG] Conexión a la base de datos cerrada correctamente")
            except Exception as e:
                print(f"[ERROR] Error al cerrar conexión a la base de datos: {e}")
        
        try:
            driver.quit()
            print("[DEBUG] Navegador cerrado correctamente")
        except Exception as e:
            print(f"[ERROR] Error al cerrar el navegador: {e}")
            
        print("[DEBUG] Proceso completado")

if __name__ == "__main__":
    # ¡AQUÍ ELEGIMOS QUÉ FUNCIÓN EJECUTAR!
    
    # Opción 1: Proceso completo (escanear directorio completo)
    # extraer_animes_jkanime()
    
    # Opción 2: Insertar un anime específico por su slug
    # Reemplaza "naruto" con el nombre del anime que quieres insertar
    # Esto insertará el anime con todos sus episodios y reproductores
    insertar_anime_por_slug("naruto")