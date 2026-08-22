#!/usr/bin/env python3
"""
NEXUS SDR-LINK - VERSIÓN MEJORADA
Sistema de análisis de cobertura y modulación QPSK
Para zonas de sombra urbana en Bogotá
"""

import numpy as np
import matplotlib.pyplot as plt
import folium
from folium import plugins
import time
from datetime import datetime

# Importar scipy para erfc
try:
    from scipy.special import erfc
except ImportError:
    def erfc(x):
        return 1 - np.erf(x)

# ============================================
# PARTE 1: CLASE DE COBERTURA (MEJORADA)
# ============================================

class CoberturaBogota:
    """
    Simulador de cobertura de señal en Bogotá
    Colores: Verde (buena), Amarilla (media), Roja (mala), Gris (zona muerta)
    """
    
    def __init__(self):
        # Coordenadas de Bogotá
        self.lat_center = 4.7110
        self.lon_center = -74.0721
        
        # Torres base simuladas (lat, lon, potencia_dBm) - AHORA CON MENOS POTENCIA
        self.torres = [
            (4.7110, -74.0721, 30),   # Centro
            (4.6300, -74.0800, 25),   # Sur (más lejos)
            (4.7900, -74.0600, 28),   # Norte (más lejos)
            (4.7200, -74.1500, 22),   # Occidente (más lejos)
            (4.7000, -74.0000, 26),   # Oriente (más lejos)
            (4.6600, -74.1000, 20),   # Sur-Occidente
            (4.7600, -74.0300, 24),   # Nor-Oriente
        ]
        
        # Factores climáticos (atenuación en dB/km)
        self.clima = {
            'despejado': 0.5,
            'lluvia': 3.0,
            'niebla': 2.0,
            'tormenta': 5.0
        }
        
        # Umbrales para colores (en dBm) - MÁS REALISTAS
        self.umbrales = {
            'excelente': -60,  # Verde
            'media': -75,      # Amarillo
            'mala': -90        # Rojo
            # Gris: < -90 (zona muerta)
        }
    
    def calcular_distancia(self, lat1, lon1, lat2, lon2):
        """Distancia en km usando fórmula de Haversine"""
        R = 6371
        lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
        c = 2 * np.arcsin(np.sqrt(a))
        return R * c
    
    def calcular_perdida_trayectoria(self, distancia, frecuencia=2400, clima='despejado'):
        """
        Modelo Okumura-Hata para entornos urbanos
        Más realista para Bogotá
        """
        if distancia < 0.01:
            return 0
        
        # Okumura-Hata para ciudad mediana
        # L = 69.55 + 26.16*log10(f) - 13.82*log10(hb) - a(hm) + (44.9 - 6.55*log10(hb))*log10(d)
        f = frecuencia  # MHz
        hb = 30  # Altura de la torre en metros
        hm = 1.5  # Altura del móvil en metros
        
        # Factor de corrección para ciudad mediana
        a_hm = (1.1 * np.log10(f) - 0.7) * hm - (1.56 * np.log10(f) - 0.8)
        
        perdida = 69.55 + 26.16 * np.log10(f) - 13.82 * np.log10(hb) - a_hm
        perdida += (44.9 - 6.55 * np.log10(hb)) * np.log10(distancia * 1000)  # distancia en km
        
        # Factor climático (atenuación adicional)
        atenuacion = self.clima.get(clima, 0.5)
        perdida += atenuacion * distancia * 2  # Atenuación por clima
        
        return perdida
    
    def calcular_intensidad_senal(self, lat, lon, clima='despejado'):
        """Potencia de señal en dBm"""
        potencia_total = -200
        
        for torre in self.torres:
            lat_t, lon_t, pot_t = torre
            distancia = self.calcular_distancia(lat, lon, lat_t, lon_t)
            
            if distancia < 0.05:  # Muy cerca a la torre
                potencia = pot_t - 5  # Pérdida mínima
            else:
                perdida = self.calcular_perdida_trayectoria(distancia, clima=clima)
                potencia = pot_t - perdida
            
            if potencia > potencia_total:
                potencia_total = potencia
        
        return max(-130, min(potencia_total, 50))
    
    def obtener_color_cobertura(self, potencia):
        """Retorna color y calidad según intensidad de señal"""
        if potencia >= self.umbrales['excelente']:
            return 'green', 'Excelente'
        elif potencia >= self.umbrales['media']:
            return 'yellow', 'Media'
        elif potencia >= self.umbrales['mala']:
            return 'red', 'Mala'
        else:
            return 'gray', 'Zona muerta'
    
    def generar_mapa(self, clima='despejado', resolucion=30):
        """Genera mapa interactivo de cobertura"""
        mapa = folium.Map(
            location=[self.lat_center, self.lon_center],
            zoom_start=11,
            tiles='OpenStreetMap'
        )
        
        lat_range = np.linspace(4.55, 4.87, resolucion)
        lon_range = np.linspace(-74.22, -73.95, resolucion)
        
        heat_data = []
        conteo_colores = {'green': 0, 'yellow': 0, 'red': 0, 'gray': 0}
        
        for lat in lat_range:
            for lon in lon_range:
                potencia = self.calcular_intensidad_senal(lat, lon, clima)
                color, calidad = self.obtener_color_cobertura(potencia)
                conteo_colores[color] += 1
                
                # Radio variable según intensidad
                radio = 5 + (potencia + 130) / 10
                radio = max(3, min(radio, 12))
                
                folium.CircleMarker(
                    location=[lat, lon],
                    radius=radio,
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.8,
                    popup=f'📍 {lat:.4f}, {lon:.4f}\n📶 Señal: {potencia:.1f} dBm\n📊 Calidad: {calidad}'
                ).add_to(mapa)
                
                heat_data.append([lat, lon, potencia + 130])
        
        # Agregar torres con mejor visualización
        for torre in self.torres:
            lat_t, lon_t, pot_t = torre
            folium.Marker(
                location=[lat_t, lon_t],
                popup=f'🏗️ Torre Base\n📡 Potencia: {pot_t} dBm',
                icon=folium.Icon(color='red', icon='tower', prefix='fa')
            ).add_to(mapa)
            
            # Círculo de cobertura aproximado de la torre
            folium.Circle(
                location=[lat_t, lon_t],
                radius=3000,  # 3 km de radio
                color='blue',
                fill=True,
                fill_color='blue',
                fill_opacity=0.05,
                popup=f'Cobertura aproximada de torre'
            ).add_to(mapa)
        
        # Capa de calor
        plugins.HeatMap(heat_data, radius=20, blur=15, min_opacity=0.3).add_to(mapa)
        
        # Título
        titulo = f'🌐 Mapa de Cobertura - Bogotá ({clima.upper()})'
        mapa.get_root().html.add_child(
            folium.Element(f'<h3 align="center" style="color:#2c3e50; font-family:Arial;">{titulo}</h3>')
        )
        
        # Leyenda mejorada
        leyenda = '''
        <div style="position: fixed; bottom: 50px; left: 50px; z-index: 1000; 
                    background-color: white; padding: 15px; border-radius: 10px;
                    border: 2px solid #2c3e50; font-family: Arial; font-size: 13px;
                    box-shadow: 0 4px 8px rgba(0,0,0,0.2);">
            <h4 style="margin:0 0 8px 0; color:#2c3e50;">📊 Leyenda</h4>
            <p style="margin:2px;"><span style="color:green; font-size:18px;">●</span> Excelente (≥ -60 dBm)</p>
            <p style="margin:2px;"><span style="color:#ffd700; font-size:18px;">●</span> Media (-75 a -60 dBm)</p>
            <p style="margin:2px;"><span style="color:red; font-size:18px;">●</span> Mala (-90 a -75 dBm)</p>
            <p style="margin:2px;"><span style="color:gray; font-size:18px;">●</span> Zona muerta (< -90 dBm)</p>
            <hr style="margin:5px 0;">
            <p style="margin:2px; font-size:12px; color:#666;">📡 Torres: <span style="color:red;">●</span> Rojo</p>
            <p style="margin:2px; font-size:12px; color:#666;">🔵 Círculo: Cobertura aprox.</p>
        </div>
        '''
        mapa.get_root().html.add_child(folium.Element(leyenda))
        
        return mapa
    
    def obtener_estadisticas(self, clima='despejado'):
        """Estadísticas de cobertura para el área"""
        lat_range = np.linspace(4.55, 4.87, 25)
        lon_range = np.linspace(-74.22, -73.95, 25)
        
        potencias = []
        colores = {'green': 0, 'yellow': 0, 'red': 0, 'gray': 0}
        
        for lat in lat_range:
            for lon in lon_range:
                potencia = self.calcular_intensidad_senal(lat, lon, clima)
                potencias.append(potencia)
                color, _ = self.obtener_color_cobertura(potencia)
                colores[color] += 1
        
        total = sum(colores.values())
        
        # Calcular estadísticas por zonas
        return {
            'potencia_promedio': np.mean(potencias),
            'potencia_max': np.max(potencias),
            'potencia_min': np.min(potencias),
            'potencia_std': np.std(potencias),
            'cobertura_excelente': (colores['green'] / total) * 100,
            'cobertura_media': (colores['yellow'] / total) * 100,
            'cobertura_mala': (colores['red'] / total) * 100,
            'zonas_muertas': (colores['gray'] / total) * 100,
            'total_puntos': total
        }


# ============================================
# PARTE 2: CLASE QPSK (MEJORADA)
# ============================================

class SimuladorQPSK:
    """Simulador de modulación QPSK con AWGN"""
    
    def __init__(self, num_symbols=2000):
        self.num_symbols = num_symbols
        self.M = 4
        self.symbols = None
        self.modulated = None
        
        self.constelacion = {
            0: (1/np.sqrt(2), 1/np.sqrt(2)),
            1: (-1/np.sqrt(2), 1/np.sqrt(2)),
            2: (1/np.sqrt(2), -1/np.sqrt(2)),
            3: (-1/np.sqrt(2), -1/np.sqrt(2))
        }
        
        self.grey_map = {0: 0, 1: 1, 2: 3, 3: 2}
        self.inverse_grey = {0: 0, 1: 1, 3: 2, 2: 3}
    
    def generar_simbolos(self):
        self.symbols = np.random.randint(0, self.M, self.num_symbols)
        return self.symbols
    
    def mapear_simbolos(self, symbols=None):
        if symbols is None:
            symbols = self.symbols
        
        modulated = np.zeros(len(symbols), dtype=complex)
        for i, sym in enumerate(symbols):
            sym_grey = self.grey_map[sym]
            real, imag = self.constelacion[sym_grey]
            modulated[i] = complex(real, imag)
        
        self.modulated = modulated
        return modulated
    
    def agregar_ruido(self, snr_db):
        potencia_senal = np.mean(np.abs(self.modulated)**2)
        snr_linear = 10**(snr_db/10)
        potencia_ruido = potencia_senal / snr_linear
        
        ruido = np.sqrt(potencia_ruido/2) * (np.random.randn(len(self.modulated)) + 
                                             1j * np.random.randn(len(self.modulated)))
        
        return self.modulated + ruido
    
    def demodular(self, signal_recibida):
        simbolos_demodulados = []
        constelacion_list = [(c[0], c[1]) for c in self.constelacion.values()]
        
        for punto in signal_recibida:
            distancias = [np.abs(complex(c[0], c[1]) - punto) for c in constelacion_list]
            idx = np.argmin(distancias)
            simbolos_demodulados.append(self.inverse_grey[idx])
        
        return np.array(simbolos_demodulados)
    
    def calcular_ber(self, originales, recibidos):
        errores = np.sum(originales != recibidos)
        return errores / len(originales)
    
    def simular(self, snr_db_range=None):
        if snr_db_range is None:
            snr_db_range = list(range(0, 21, 2))
        
        self.generar_simbolos()
        self.mapear_simbolos()
        
        resultados = {'snr': [], 'ber': []}
        
        for snr in snr_db_range:
            signal_recibida = self.agregar_ruido(snr)
            simbolos_recibidos = self.demodular(signal_recibida)
            ber = self.calcular_ber(self.symbols, simbolos_recibidos)
            resultados['snr'].append(snr)
            resultados['ber'].append(ber)
        
        return resultados
    
    def graficar_constelacion(self, snr_db=15):
        self.generar_simbolos()
        self.mapear_simbolos()
        signal_recibida = self.agregar_ruido(snr_db)
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        
        # Constelación ideal
        ax1.scatter(self.modulated.real, self.modulated.imag, 
                   alpha=0.6, s=25, color='blue', label='Ideal')
        ax1.set_title('Constelación Ideal QPSK', fontsize=14, fontweight='bold')
        ax1.set_xlabel('I (Componente en fase)')
        ax1.set_ylabel('Q (Componente en cuadratura)')
        ax1.grid(True, alpha=0.3)
        ax1.axis('equal')
        ax1.legend()
        ax1.set_xlim([-1.5, 1.5])
        ax1.set_ylim([-1.5, 1.5])
        
        # Constelación con ruido
        ax2.scatter(signal_recibida.real, signal_recibida.imag, 
                   alpha=0.5, s=20, color='red', label=f'SNR={snr_db} dB')
        ax2.scatter(self.modulated.real, self.modulated.imag, 
                   alpha=0.7, s=60, color='blue', marker='x', label='Puntos Ideales')
        ax2.set_title(f'Constelación con Ruido AWGN (SNR={snr_db} dB)', 
                     fontsize=14, fontweight='bold')
        ax2.set_xlabel('I (Componente en fase)')
        ax2.set_ylabel('Q (Componente en cuadratura)')
        ax2.grid(True, alpha=0.3)
        ax2.axis('equal')
        ax2.legend()
        ax2.set_xlim([-1.5, 1.5])
        ax2.set_ylim([-1.5, 1.5])
        
        plt.tight_layout()
        return fig
    
    def graficar_ber(self, resultados=None):
        if resultados is None:
            resultados = self.simular()
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        ax.semilogy(resultados['snr'], resultados['ber'], 'b-o', 
                   linewidth=2, markersize=8, label='QPSK Simulado')
        
        # Curva teórica para QPSK en AWGN
        snr_teorico = np.array(resultados['snr'])
        try:
            ber_teorico = 0.5 * erfc(np.sqrt(10**(snr_teorico/10)))
        except:
            ber_teorico = 0.5 * (1 - np.erf(np.sqrt(10**(snr_teorico/10))))
        
        ax.semilogy(snr_teorico, ber_teorico, 'r--', 
                   linewidth=2, label='QPSK Teórico (AWGN)')
        
        ax.set_title('BER vs SNR para Modulación QPSK', fontsize=14, fontweight='bold')
        ax.set_xlabel('SNR (dB)', fontsize=12)
        ax.set_ylabel('BER (Tasa de Error de Bit)', fontsize=12)
        ax.grid(True, which='both', linestyle='--', alpha=0.5)
        ax.set_ylim([1e-5, 1])
        ax.legend(fontsize=11)
        
        return fig


# ============================================
# PARTE 3: PROGRAMA PRINCIPAL
# ============================================

class NexusSDRLink:
    """Programa principal que integra cobertura y QPSK"""
    
    def __init__(self):
        self.cobertura = CoberturaBogota()
        self.qpsk = SimuladorQPSK(2000)
        self.resultados = {}
        self.tiempo_inicio = None
    
    def mostrar_banner(self):
        print("="*70)
        print("  ███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗")
        print("  ████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝")
        print("  ██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║███████╗")
        print("  ██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║╚════██║")
        print("  ██║ ╚████║███████╗██╔╝ ██╗╚██████╔╝███████║")
        print("  ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝")
        print("="*70)
        print("  📡 NEXUS SDR-LINK - ANÁLISIS DE COBERTURA Y QPSK")
        print("  🏙️  Bogotá - Zonas de sombra urbana")
        print("="*70)
        print()
    
    def ejecutar_analisis_completo(self, clima='despejado', snr_qpsk=15):
        self.tiempo_inicio = time.time()
        self.mostrar_banner()
        
        print("📋 INICIO DE ANÁLISIS")
        print(f"   📅 Fecha/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   🌤️  Clima: {clima.upper()}")
        print(f"   📡 SNR QPSK: {snr_qpsk} dB")
        print("-"*70)
        
        # 1. COBERTURA
        print("\n📡 [1/3] ANALIZANDO COBERTURA EN BOGOTÁ...")
        
        print("   → Generando mapa interactivo...")
        mapa = self.cobertura.generar_mapa(clima=clima, resolucion=25)
        nombre_mapa = f'mapa_cobertura_{clima}.html'
        mapa.save(nombre_mapa)
        print(f"   ✅ Mapa guardado: {nombre_mapa}")
        
        print("   → Calculando estadísticas...")
        stats = self.cobertura.obtener_estadisticas(clima=clima)
        
        print("\n   📊 RESULTADOS DE COBERTURA:")
        print(f"      ├─ Potencia promedio: {stats['potencia_promedio']:.2f} dBm")
        print(f"      ├─ Potencia máxima: {stats['potencia_max']:.2f} dBm")
        print(f"      ├─ Potencia mínima: {stats['potencia_min']:.2f} dBm")
        print(f"      ├─ Desviación estándar: {stats['potencia_std']:.2f} dB")
        print(f"      ├─ Excelente (🟢): {stats['cobertura_excelente']:.1f}%")
        print(f"      ├─ Media (🟡): {stats['cobertura_media']:.1f}%")
        print(f"      ├─ Mala (🔴): {stats['cobertura_mala']:.1f}%")
        print(f"      └─ Zona muerta (⬜): {stats['zonas_muertas']:.1f}%")
        
        # 2. QPSK
        print("\n📡 [2/3] SIMULANDO MODULACIÓN QPSK...")
        
        print("   → Ejecutando simulación...")
        resultados_qpsk = self.qpsk.simular()
        
        print("   → Generando gráfica BER...")
        fig_ber = self.qpsk.graficar_ber(resultados_qpsk)
        nombre_ber = f'ber_qpsk_{clima}.png'
        fig_ber.savefig(nombre_ber, dpi=150, bbox_inches='tight')
        print(f"   ✅ Gráfica BER guardada: {nombre_ber}")
        
        print(f"   → Generando constelación (SNR={snr_qpsk} dB)...")
        fig_const = self.qpsk.graficar_constelacion(snr_qpsk)
        nombre_const = f'constelacion_qpsk_{clima}.png'
        fig_const.savefig(nombre_const, dpi=150, bbox_inches='tight')
        print(f"   ✅ Constelación guardada: {nombre_const}")
        
        if snr_qpsk in resultados_qpsk['snr']:
            idx = resultados_qpsk['snr'].index(snr_qpsk)
            ber_actual = resultados_qpsk['ber'][idx]
            print(f"\n   📊 RESULTADOS QPSK:")
            print(f"      ├─ SNR analizado: {snr_qpsk} dB")
            print(f"      ├─ BER obtenido: {ber_actual:.2e}")
            calidad = 'Excelente' if ber_actual < 1e-4 else 'Aceptable' if ber_actual < 1e-3 else 'Mala'
            print(f"      └─ Calidad: {calidad}")
        
        # 3. PUNTOS DE INTERÉS
        print("\n📍 [3/3] ANALIZANDO PUNTOS DE INTERÉS EN BOGOTÁ...")
        
        puntos_interes = [
            (4.7110, -74.0721, "Centro"),
            (4.6500, -74.0800, "Sur"),
            (4.7700, -74.0600, "Norte"),
            (4.7200, -74.1300, "Occidente"),
            (4.7000, -74.0200, "Oriente"),
            (4.6800, -74.0950, "Bosa"),
            (4.7400, -74.0450, "Usaquén"),
            (4.6300, -74.1100, "Kennedy"),
            (4.8000, -74.0400, "Suba"),
            (4.5900, -74.0700, "Usme")
        ]
        
        for lat, lon, nombre in puntos_interes:
            potencia = self.cobertura.calcular_intensidad_senal(lat, lon, clima)
            color, calidad = self.cobertura.obtener_color_cobertura(potencia)
            emoji = {'green': '🟢', 'yellow': '🟡', 'red': '🔴', 'gray': '⬜'}[color]
            print(f"      {emoji} {nombre:12s}: {potencia:6.1f} dBm - {calidad}")
        
        # RESUMEN
        tiempo_total = time.time() - self.tiempo_inicio
        
        print("\n" + "="*70)
        print("✅ ANÁLISIS COMPLETADO")
        print(f"   ⏱️  Tiempo total: {tiempo_total:.2f} segundos")
        print(f"   📁 Archivos generados:")
        print(f"      📄 {nombre_mapa}")
        print(f"      📄 {nombre_ber}")
        print(f"      📄 {nombre_const}")
        print("="*70)
        
        self.resultados = {
            'cobertura_stats': stats,
            'qpsk_resultados': resultados_qpsk,
            'clima': clima,
            'snr': snr_qpsk,
            'archivos': {
                'mapa': nombre_mapa,
                'ber': nombre_ber,
                'constelacion': nombre_const
            },
            'tiempo': tiempo_total
        }
        
        return self.resultados


def main():
    nexus = NexusSDRLink()
    
    while True:
        print("\n" + "="*55)
        print("  📡 NEXUS SDR-LINK - MENÚ PRINCIPAL")
        print("="*55)
        print("  1. Análisis completo (Clima despejado)")
        print("  2. Análisis completo (Clima lluvioso)")
        print("  3. Análisis completo (Clima con niebla)")
        print("  4. Análisis completo (Clima tormenta)")
        print("  5. Solo mapa de cobertura")
        print("  6. Solo simulación QPSK")
        print("  7. Comparar todos los climas")
        print("  8. Salir")
        print("="*55)
        
        opcion = input("\nOpción (1-8): ").strip()
        
        if opcion == '1':
            nexus.ejecutar_analisis_completo(clima='despejado', snr_qpsk=15)
        elif opcion == '2':
            nexus.ejecutar_analisis_completo(clima='lluvia', snr_qpsk=12)
        elif opcion == '3':
            nexus.ejecutar_analisis_completo(clima='niebla', snr_qpsk=10)
        elif opcion == '4':
            nexus.ejecutar_analisis_completo(clima='tormenta', snr_qpsk=8)
        elif opcion == '5':
            cobertura = CoberturaBogota()
            mapa = cobertura.generar_mapa('despejado')
            mapa.save('mapa_cobertura_solo.html')
            print("✅ Mapa guardado: mapa_cobertura_solo.html")
        elif opcion == '6':
            qpsk = SimuladorQPSK(2000)
            resultados = qpsk.simular()
            fig_ber = qpsk.graficar_ber(resultados)
            fig_ber.savefig('ber_qpsk_solo.png')
            print("✅ Gráfica BER guardada: ber_qpsk_solo.png")
            fig_const = qpsk.graficar_constelacion(15)
            fig_const.savefig('constelacion_qpsk_solo.png')
            print("✅ Constelación guardada: constelacion_qpsk_solo.png")
        elif opcion == '7':
            print("\n🔄 Comparando climas...")
            for clima in ['despejado', 'lluvia', 'niebla', 'tormenta']:
                print(f"\n--- {clima.upper()} ---")
                stats = nexus.cobertura.obtener_estadisticas(clima=clima)
                print(f"   Excelente: {stats['cobertura_excelente']:.1f}%")
                print(f"   Media:     {stats['cobertura_media']:.1f}%")
                print(f"   Mala:      {stats['cobertura_mala']:.1f}%")
                print(f"   Zona muerta: {stats['zonas_muertas']:.1f}%")
        elif opcion == '8':
            print("👋 ¡Hasta luego!")
            break
        else:
            print("❌ Opción inválida. Intente nuevamente.")


if __name__ == "__main__":
    main()