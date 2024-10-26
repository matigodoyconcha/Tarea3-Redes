import struct
import socket

def calcular_checksum(header):
    checksum = 0
    for i in range(0, len(header), 2):
        word = (header[i] << 8) + (header[i + 1] if i + 1 < len(header) else 0)
        checksum += word

    checksum = (checksum >> 16) + (checksum & 0xFFFF)  # Sumar los desbordamientos
    checksum = ~checksum & 0xFFFF  # Complemento a uno
    return checksum

def crear_datagrama_ip(src_ip, dst_ip, protocol, mensaje, ID, flags, offset):
    version = 4
    ihl = 5  # Longitud del encabezado en palabras de 32 bits
    tos = 0  # Tipo de servicio
    payload_length = len(mensaje)  # Longitud de la carga útil
    total_length = 20 + payload_length  # Longitud total del datagrama

    if total_length > 65535:
        raise ValueError("El tamaño total del datagrama excede el máximo permitido.")
    if ID < 0 or ID > 65535:
        raise ValueError("El ID debe estar entre 0 y 65535.")
    if flags < 0 or flags > 7:  # Solo hay 3 bits para flags
        raise ValueError("Las flags deben estar entre 0 y 7.")
    if offset < 0 or offset > 8191:  # Máximo desplazamiento de fragmento
        raise ValueError("El offset debe estar entre 0 y 8191.")
    ttl = 64  # TTL dentro del rango
    if ttl < 0 or ttl > 255:
        raise ValueError("TTL debe estar entre 0 y 255.")
    if protocol < 0 or protocol > 255:
        raise ValueError("El protocolo debe estar entre 0 y 255.")

    src_ip_bin = socket.inet_aton(src_ip)
    dst_ip_bin = socket.inet_aton(dst_ip)

    ip_header = struct.pack('!BBHHHBBH4s4s',
                             (version << 4) + ihl,  # Versión + IHL
                             tos,
                             total_length,
                             ID,
                             (flags << 13) + offset,
                             ttl,
                             protocol,
                             0,  # El checksum se calcula más tarde
                             src_ip_bin,
                             dst_ip_bin)

    header_checksum = calcular_checksum(ip_header)
    ip_header = struct.pack('!BBHHHBBH4s4s',
                             (version << 4) + ihl,
                             tos,
                             total_length,
                             ID,
                             (flags << 13) + offset,
                             ttl,
                             protocol,
                             header_checksum,
                             src_ip_bin,
                             dst_ip_bin)

    datagrama = ip_header + mensaje.encode()  # Asegúrate de codificar el mensaje

    return datagrama

# Definir el mensaje de prueba
mensaje_de_prueba = "Estoy muy feliz de que esto este funcionando, alo que pasa " * 8

# Parámetros para el datagrama
src_ip = "127.0.0.1"  # IP de origen
dst_ip = "10.42.76.32"  # IP de destino
protocol = 17  # Protocolo UDP
ID = 1  # Identificación del datagrama
flags = 0  # Flags (0 para el último fragmento)
offset = 0  # Offset (0 para el primer fragmento)

# Crear el datagrama
try:
    datagrama = crear_datagrama_ip(src_ip, dst_ip, protocol, mensaje_de_prueba, ID, flags, offset)
    print(f"Tamaño del datagrama creado: {len(datagrama)} bytes")
    
    # Crear un socket UDP
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        # Enviar el datagrama al socket en puerto 5000
        s.sendto(datagrama, (src_ip, 5000))
        print("Datagrama enviado al socket.")
except ValueError as e:
    print(f"Error: {e}")
except Exception as e:
    print(f"Se produjo un error al enviar el datagrama: {e}")
