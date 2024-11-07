import struct
import socket
import threading
import queue
import time
import sys


class Enlace:
    def __init__(self, ip, direccion, MTU):
        self.ip = ip
        self.direccion = direccion
        self.MTU = MTU

class Router:
    def __init__(self, ip, puerto, enlaces):
        # Inicialización del socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((ip, puerto))
        
        self.ip = ip
        self.puerto = puerto
        self.enlaces = enlaces
        
        # Buffer para mensajes destinados al router
        self.buffer = []
        
        # Cola de mensajes a reenviar
        self.cola = queue.Queue()
        
        # Mutex para proteger el acceso a la cola
        self.cola_mutex = threading.Lock()
        
        # Hilo para procesar la cola
        self.thread = threading.Thread(target=self.procesar_cola)
        self.thread.start()

    def buscar_ip(self, target_ip):
        for enlace in self.enlaces:
            if enlace.ip == target_ip:
                return enlace
        return None

    def enviar(self, datagrama, target):
        src_ip, dst_ip, protocol, mensaje, identification, flags, offset, ttl = self.desempaquetar_datagrama_ip(datagrama)

        if not self.enlaces:
            print("No hay enlaces disponibles. Descartando mensaje.")
            return

        enlace = self.buscar_ip(target)
        if enlace:
            # Lo mando por ahí, ya sea entero o fragmentado
            if len(datagrama) <= enlace.MTU:
                print("Mensaje cabe dentro del MTU, enviando directamente")
                self.socket.sendto(datagrama, (enlace.ip, enlace.direccion))
                time.sleep(1)
            else:
                # Fragmentar el mensaje si es necesario
                fragmentos = self.fragmentar_mensaje(datagrama, enlace.MTU)
                print(f"Mensaje demasiado grande, fragmentando en {len(fragmentos)} mensajes")
                for fragmento in fragmentos:
                    self.socket.sendto(fragmento, (enlace.ip, enlace.direccion))
                    time.sleep(1)
                print("TERMINAMOOOOOOOOS")
        else:
            enlace = self.enlaces[0]
            if len(datagrama) <= enlace.MTU:
                print("Mensaje cabe dentro del MTU, enviando directamente")
                self.socket.sendto(datagrama, (enlace.ip, enlace.direccion))
                time.sleep(1)
            else:
                largo_msg = len(datagrama)
                nuevo_offset = offset
                while largo_msg > 0:
                    for enlace in self.enlaces:
                        actualMTU = enlace.MTU
                        if largo_msg > actualMTU:
                            fragmento, mensaje,nuevo_offset = dividir_mensaje(mensaje, enlace.MTU, src_ip, dst_ip, protocol, identification, 1, nuevo_offset)
                            largo_msg = len(mensaje)
                            if largo_msg == 0:
                                break
                            print(f"Se lo mandamos a: {enlace.ip}, {enlace.direccion}")
                            self.socket.sendto(fragmento, (enlace.ip, enlace.direccion))
                            time.sleep(1)
                        else:
                            print("QUEDA EL ULTIMO")
                            mensaje = crear_datagrama_ip(src_ip, dst_ip, protocol, mensaje, identification, flags, nuevo_offset)
                            self.socket.sendto(mensaje, (enlace.ip, enlace.direccion))
                            time.sleep(1)
                            mensaje = ""
                            largo_msg = 0
                            break


    def recibir(self):
        while True:
            # Recibir mensaje desde el socket
            data, addr = self.socket.recvfrom(65535)  # Recibir hasta 65535 bytes (máximo tamaño del datagrama IP)
            print(f"Mensaje recibido de {addr}, encolando para procesamiento")
            
            # Proteger el acceso a la cola con un mutex
            with self.cola_mutex:
                self.cola.put(data)  # Encolar el datagrama completo para procesarlo más tarde

    def procesar_cola(self):
        fragmentos_por_id = {}
        tiempos_por_id = {}
        timeout = 10  # Tiempo límite para esperar fragmentos faltantes, en segundos

        while True:
            datagrama = None
            with self.cola_mutex:
                if not self.cola.empty():
                    datagrama = self.cola.get()

            if datagrama:
                # Desempaquetar el datagrama
                src_ip, dst_ip, protocolo, mensaje, ID, flags, offset, ttl = self.desempaquetar_datagrama_ip(datagrama)
                

                if dst_ip == self.ip:
                    print(f"Procesando fragmento para este router: ID {ID}, offset {offset}, flags {flags}, ttl {ttl}")

                    if ID not in fragmentos_por_id:
                        fragmentos_por_id[ID] = {}
                        

                    fragmentos_por_id[ID][offset] = mensaje
                    tiempos_por_id[ID] = time.time()

                    if flags == 0:
                        print(f"Último fragmento recibido para ID {ID}. Verificando si llegaron todos los fragmentos...")
                        tamaño_esperado = sum(len(fragmentos_por_id[ID][i]) for i in fragmentos_por_id[ID])
                        print(f"Tamaño esperado: {tamaño_esperado}")
                        print((offset* 8 + len(mensaje)))

                        if (offset*8+ len(mensaje)) == tamaño_esperado:
                            mensaje_completo = b''.join(fragmentos_por_id[ID][i] for i in sorted(fragmentos_por_id[ID]))
                            self.buffer.append(mensaje_completo)
                            print(f"Mensaje completo reensamblado y guardado en buffer (ID {ID})")
                            print(self.buffer[-1].decode('utf-8') == "Estoy muy feliz de que esto este funcionando, alo que pasa " * 8)
                            del fragmentos_por_id[ID]
                            del tiempos_por_id[ID]
                        else:
                            print(f"Fragmentos faltantes para ID {ID}, esperando...")
                else:
                    print(f"Mensaje no destinado a este router, reenviando (ID {ID}), ip target {dst_ip}, con un offset de {offset}")
                    if ttl <= 0:
                        #Se descarta el mensaje si es que ttl es menor o igual a 0.
                        continue
                    self.enviar(datagrama, dst_ip)

            for msg_id in list(tiempos_por_id):
                if time.time() - tiempos_por_id[msg_id] > timeout:
                    print(f"Tiempo límite excedido para el mensaje ID {msg_id}. Descartando...")
                    del fragmentos_por_id[msg_id]
                    del tiempos_por_id[msg_id]

            time.sleep(1)

    def desempaquetar_datagrama_ip(self, data):
        header = struct.unpack('!BBHHHBBH4s4s', data[:20])
        version_ihl = header[0]
        version = version_ihl >> 4
        ihl = version_ihl & 0xF
        total_length = header[2]
        identification = header[3]
        flags_fragment_offset = header[4]
        ttl = header[5]
        protocol = header[6]
        src_ip = socket.inet_ntoa(header[8])
        dst_ip = socket.inet_ntoa(header[9])
        mensaje = data[20:total_length]

        flags = flags_fragment_offset >> 13
        offset = flags_fragment_offset & 0x1FFF

        return src_ip, dst_ip, protocol, mensaje, identification, flags, offset, ttl

    def fragmentar_mensaje(self, datagrama, MTU):
        src_ip, dst_ip, protocol, mensaje, ID, flags, offset, ttl = self.desempaquetar_datagrama_ip(datagrama)
        fragmentos = []
        max_payload_size = (MTU - 20) - (MTU - 20)%8 # Restar tamaño de la cabecera IP (20 bytes)
        offset_actual = offset

        # Iterar a través del mensaje para crear fragmentos
        for i in range(0, len(mensaje), max_payload_size):
            # Extraer el fragmento de mensaje correspondiente
            fragmento = mensaje[i:i + max_payload_size]
            
            # El flag "más fragmentos" (MF) debe ser 1 si no es el último fragmento
            mf_flag = 1 if (i + max_payload_size) < len(mensaje) else 0
            
            # Crear el fragmento con el offset correcto en unidades de 8 bytes
            datagrama_fragmentado = crear_datagrama_ip(src_ip, dst_ip, protocol, fragmento, ID, mf_flag, offset_actual // 8)
            print(f"Creamos un mensaje con flag:{mf_flag}")
            
            # Añadir el fragmento a la lista de fragmentos
            fragmentos.append(datagrama_fragmentado)
            
            # Actualizar el offset para el siguiente fragmento
            offset_actual += len(fragmento)
            
        return fragmentos

def crear_datagrama_ip(src_ip, dst_ip, protocol, mensaje, ID, flags, offset):
    version = 4
    ihl = 5
    tos = 0
    total_length = 20 + len(mensaje)
    identification = ID
    flags = flags
    fragment_offset = offset
    ttl = 10
    header_checksum = 0

    print(f"version: {version}, ihl: {ihl}, tos: {tos}, total_length: {total_length}, identification: {identification}")
    print(f"flags: {flags}, fragment_offset: {fragment_offset}, ttl: {ttl}, protocol: {protocol}")

    src_ip_bin = socket.inet_aton(src_ip)
    dst_ip_bin = socket.inet_aton(dst_ip)

    ip_header = struct.pack('!BBHHHBBH4s4s',
                            (version << 4) + ihl,
                            tos,
                            total_length,
                            identification,
                            (flags << 13) + fragment_offset,
                            ttl,
                            protocol,
                            header_checksum,
                            src_ip_bin,
                            dst_ip_bin)

    header_checksum = calcular_checksum(ip_header)
    ip_header = struct.pack('!BBHHHBBH4s4s',
                            (version << 4) + ihl,
                            tos,
                            total_length,
                            identification,
                            (flags << 13) + fragment_offset,
                            ttl,
                            protocol,
                            header_checksum,
                            src_ip_bin,
                            dst_ip_bin)

    datagrama = ip_header + mensaje
    return datagrama

def calcular_checksum(header):
    checksum = 0
    for i in range(0, len(header), 2):
        word = (header[i] << 8) + (header[i + 1] if i + 1 < len(header) else 0)
        checksum += word

    checksum = (checksum >> 16) + (checksum & 0xFFFF)
    checksum = ~checksum & 0xFFFF
    return checksum

def dividir_mensaje(mensaje, MTU, src_ip, dst_ip, protocol, ID, flags, offset):
    header_size = 20
    max_payload_size = (MTU - header_size)-(MTU - header_size)%8

    # Fragmentar el mensaje en la parte del payload
    fragmento = mensaje[:max_payload_size]
    mensaje_restante = mensaje[max_payload_size:]
    
    # El offset debe estar en unidades de 8 bytes
    datagrama_fragmentado = crear_datagrama_ip(src_ip, dst_ip, protocol, fragmento, ID, flags, offset)
    
    # El nuevo offset para el siguiente fragmento debe ser ajustado
    nuevo_offset = offset + len(fragmento)//8
    
    print(f"Nuevo fragmento que envia: {fragmento}, con flags: {flags}")
    return datagrama_fragmentado, mensaje_restante, nuevo_offset


def main():
    # Obtener los argumentos del main
    args = sys.argv[1:]
    mi_ip_puerto = args[0]
    enlaces_args = args[1:]

    # Procesamos los argumentos y creamos una clase de Enlace por cada enlace
    mi_ip, mi_puerto = mi_ip_puerto.split(':')
    enlaces = []
    for enlace_str in enlaces_args:
        ip, puerto, mtu = enlace_str.split(':')
        enlace = Enlace(ip, int(puerto), int(mtu))
        enlaces.append(enlace)
    
    # Ordenamos según MTU
    enlaces = sorted(enlaces, key=lambda enlace: enlace.MTU, reverse=True)
    # Inicializamos el Router
    router = Router(mi_ip, int(mi_puerto), enlaces)

    # Ponemos el router a recibir
    router.recibir()

# Se ejecuta la función main.
if __name__ == "__main__":
    main()
