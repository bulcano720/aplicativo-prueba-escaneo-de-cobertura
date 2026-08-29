#!/usr/bin/env python3
"""
NEXUS SDR-LINK - VERSIÓN FINAL CON AUTO-REFRESCO CADA 5 MINUTOS
Sistema de análisis de cobertura y modulación QPSK
Para zonas de sombra urbana en Bogotá
"""

import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
import folium
from streamlit_folium import st_folium
import pandas as pd
from datetime import datetime
import math
import random

from io import BytesIO
from PIL import Image, ImageDraw
import hashlib

# Configurar página
st.set_page_config(
    page_title="NEXUS SDR-LINK",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# CLASE DE COBERTURA (CORREGIDA)
# ============================================
class CoberturaBogota:
    def __init__(self):
        self.lat_center = 4.7110
        self.lon_center = -74.0721
        
        # Torres base
        self.torres = [
            (4.7110, -74.0721, 50),   # Centro
            (4.6600, -74.0900, 45),   # Sur
            (4.7700, -74.0500, 48),   # Norte
            (4.7200, -74.1400, 42),   # Occidente
            (4.7000, -74.0100, 44),   # Oriente
            (4.6700, -74.1000, 40),   # Bosa
            (4.7500, -74.0300, 43),   # Usaquén
            (4.6300, -74.0700, 38),   # Usme
            (4.6900, -74.1200, 41),   # Kennedy
            (4.7900, -74.0400, 39),   # Suba
        ]
        
        # Obstáculos urbanos (edificios)
        self.obstaculos = [
            (4.7100, -74.0800, 500, 80),   # Centro financiero
            (4.6800, -74.0800, 600, 100),  # Zona Industrial
            (4.7500, -74.0600, 700, 90),   # Norte (Chicó)
            (4.6700, -74.1100, 550, 85),   # Kennedy
            (4.7300, -74.0900, 650, 95),   # Salitre
            (4.6500, -74.0500, 500, 75),   # Usme
            (4.7000, -74.0300, 600, 88),   # Chapinero
        ]
        
        self.clima = {
            'despejado': 0.0,
            'lluvia': 12,
            'niebla': 6,
            'tormenta': 22
        }
        
        self.umbrales = {
            'excelente': -55,  
            'media': -75,      
            'mala': -90        
        }

    def calcular_distancia_metros(self, lat1, lon1, lat2, lon2):
        R = 6371000
        lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
        c = 2 * np.arcsin(np.sqrt(a))
        return R * c

    def calcular_intensidad_senal_con_tiempo(self, lat, lon, clima='despejado', hora_actual=0):
        # Cambiamos el divisor de 2 (horas) a 5 (minutos)
        semilla_str = f"{clima}-{hora_actual // 5}"
        semilla = int(hashlib.md5(semilla_str.encode()).hexdigest(), 16) % 10000
        random.seed(semilla)
        
        variacion_max = 0
        factor_degradacion = 0
        if clima == 'despejado':
            variacion_max = 5
        elif clima == 'lluvia':
            variacion_max = 10
            factor_degradacion = 5
        elif clima == 'niebla':
            variacion_max = 8
            factor_degradacion = 8
        elif clima == 'tormenta':
            variacion_max = 15
            factor_degradacion = 15
        
        mejor_potencia = -200
        frecuencia_mhz = 700
        
        for torre in self.torres:
            lat_t, lon_t, pot_t = torre
            distancia = self.calcular_distancia_metros(lat, lon, lat_t, lon_t)
            
            if distancia < 20:
                return -120
            
            perdida = 20 * np.log10(distancia) + 20 * np.log10(frecuencia_mhz) - 27.55
            senal = pot_t - perdida - factor_degradacion
            
            senal += random.uniform(-variacion_max, variacion_max)
            
            if senal > mejor_potencia:
                mejor_potencia = senal
        
        return max(-120, min(mejor_potencia, 50))

    def calcular_intensidad_senal(self, lat, lon, clima='despejado'):
        mejor_potencia = -200
        frecuencia_mhz = 700
        atenuacion_clima = self.clima.get(clima, 0)
        
        for torre in self.torres:
            lat_t, lon_t, pot_t = torre
            distancia = self.calcular_distancia_metros(lat, lon, lat_t, lon_t)
            
            if distancia < 20:
                return -120
            
            perdida = 20 * np.log10(distancia) + 20 * np.log10(frecuencia_mhz) - 27.55
            senal = pot_t - perdida - atenuacion_clima
            
            for obs_lat, obs_lon, obs_radio, obs_altura in self.obstaculos:
                dist_obs = self.calcular_distancia_metros(lat, lon, obs_lat, obs_lon)
                if dist_obs < obs_radio:
                    senal -= (obs_altura * 1.5)
                elif dist_obs < obs_radio * 2.5:
                    factor_perdida = obs_altura * (1 - (dist_obs / (obs_radio * 2.5)))
                    senal -= factor_perdida
            
            if senal > mejor_potencia:
                mejor_potencia = senal
        
        return max(-120, min(mejor_potencia, 50))
    
    def obtener_color_cobertura(self, potencia):
        if potencia >= self.umbrales['excelente']:
            return 'green', 'Excelente', 0.60
        elif potencia >= self.umbrales['media']:
            return 'yellow', 'Media', 0.70
        elif potencia >= self.umbrales['mala']:
            return 'red', 'Mala', 0.75
        else:
            return 'gray', 'Zona muerta', 0.85
    
    def generar_mapa(self, clima='despejado', resolucion=45):
        """Genera el mapa. IMPORTANTE: Devuelve el mapa SIEMPRE."""
        mapa = folium.Map(
            location=[self.lat_center, self.lon_center],
            zoom_start=12,
            tiles='OpenStreetMap'
        )
        
        lat_range = np.linspace(4.60, 4.80, resolucion)
        lon_range = np.linspace(-74.16, -73.98, resolucion)
        
        for lat in lat_range:
            for lon in lon_range:
                potencia = self.calcular_intensidad_senal_con_tiempo(lat, lon, clima, datetime.now().minute)
                color, calidad, opacidad = self.obtener_color_cobertura(potencia)
                
                folium.CircleMarker(
                    location=[lat, lon],
                    radius=5,
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=opacidad,
                    weight=0,
                    popup=f'📍 {lat:.4f}, {lon:.4f}\n📶 Señal: {potencia:.1f} dBm\n📊 Calidad: {calidad}'
                ).add_to(mapa)
        
        for torre in self.torres:
            lat_t, lon_t, pot_t = torre
            folium.Marker(
                location=[lat_t, lon_t],
                popup=f'🏗️ Torre\n📡 {pot_t} dBm',
                icon=folium.Icon(color='darkred', icon='tower', prefix='fa')
            ).add_to(mapa)
        
        for obs_lat, obs_lon, obs_radio, obs_altura in self.obstaculos:
            folium.Circle(
                location=[obs_lat, obs_lon],
                radius=obs_radio,
                color='black',
                fill=True,
                fill_color='black',
                fill_opacity=0.15,
                weight=0,
                popup=f'🏢 Edificio (Altura: {obs_altura}m)'
            ).add_to(mapa)
        
        return mapa
    
    def obtener_estadisticas(self, clima='despejado'):
        hora_actual = datetime.now().minute
        
        lat_range = np.linspace(4.55, 4.87, 15)
        lon_range = np.linspace(-74.22, -73.92, 15)
        
        potencias = []
        colores = {'green': 0, 'yellow': 0, 'red': 0, 'gray': 0}
        
        for lat in lat_range:
            for lon in lon_range:
                potencia = self.calcular_intensidad_senal_con_tiempo(lat, lon, clima, hora_actual)
                potencias.append(potencia)
                color, _, _ = self.obtener_color_cobertura(potencia)
                colores[color] += 1
        
        total = sum(colores.values())
        
        return {
            'potencia_promedio': np.mean(potencias),
            'potencia_max': np.max(potencias),
            'potencia_min': np.min(potencias),
            'cobertura_excelente': (colores['green'] / total) * 100 if total > 0 else 0,
            'cobertura_media': (colores['yellow'] / total) * 100 if total > 0 else 0,
            'cobertura_mala': (colores['red'] / total) * 100 if total > 0 else 0,
            'zonas_muertas': (colores['gray'] / total) * 100 if total > 0 else 0
        }


# ============================================
# CLASE QPSK
# ============================================
class SimuladorQPSK:
    def __init__(self, num_symbols=1000):
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
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
        
        ax1.scatter(self.modulated.real, self.modulated.imag, 
                   alpha=0.6, s=25, color='blue')
        ax1.set_title('Constelación Ideal QPSK')
        ax1.set_xlabel('I')
        ax1.set_ylabel('Q')
        ax1.grid(True, alpha=0.3)
        ax1.axis('equal')
        ax1.set_xlim([-1.5, 1.5])
        ax1.set_ylim([-1.5, 1.5])
        
        ax2.scatter(signal_recibida.real, signal_recibida.imag, 
                   alpha=0.5, s=20, color='red')
        ax2.scatter(self.modulated.real, self.modulated.imag, 
                   alpha=0.7, s=50, color='blue', marker='x')
        ax2.set_title(f'Constelación con Ruido (SNR={snr_db} dB)')
        ax2.set_xlabel('I')
        ax2.set_ylabel('Q')
        ax2.grid(True, alpha=0.3)
        ax2.axis('equal')
        ax2.set_xlim([-1.5, 1.5])
        ax2.set_ylim([-1.5, 1.5])
        
        plt.tight_layout()
        return fig
    
    def graficar_ber(self, resultados=None):
        if resultados is None:
            resultados = self.simular()
        
        fig, ax = plt.subplots(figsize=(8, 5))
        
        ax.semilogy(resultados['snr'], resultados['ber'], 'b-o', 
                   linewidth=2, markersize=8, label='Simulado')
        
        try:
            from scipy.special import erfc
            snr_teorico = np.array(resultados['snr'])
            ber_teorico = 0.5 * erfc(np.sqrt(10**(snr_teorico/10)))
            ax.semilogy(snr_teorico, ber_teorico, 'r--', 
                       linewidth=2, label='Teórico')
        except:
            pass
        
        ax.set_title('BER vs SNR - QPSK')
        ax.set_xlabel('SNR (dB)')
        ax.set_ylabel('BER')
        ax.grid(True, which='both', linestyle='--', alpha=0.5)
        ax.set_ylim([1e-5, 1])
        ax.legend()
        
        return fig


# ============================================
# INTERFAZ PRINCIPAL
# ============================================

cobertura = CoberturaBogota()

def main():
    st.title("📡 NEXUS SDR-LINK")
    st.subheader("Sistema de Análisis de Cobertura y Modulación QPSK")
    st.caption(f"🏙️ Bogotá - Zonas de sombra urbana | {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    
    # Sidebar
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/000000/antenna.png", width=80)
        st.markdown("## ⚙️ Configuración")
        
        clima = st.selectbox(
            "🌤️ Clima",
            options=['despejado', 'lluvia', 'niebla', 'tormenta'],
            format_func=lambda x: {
                'despejado': '☀️ Despejado',
                'lluvia': '🌧️ Lluvia',
                'niebla': '🌫️ Niebla',
                'tormenta': '⛈️ Tormenta'
            }[x]
        )
        
        snr_qpsk = st.slider(
            "📡 SNR QPSK (dB)",
            min_value=0,
            max_value=25,
            value=15,
            step=1
        )
        
        resolucion = st.slider(
            "🔍 Resolución",
            min_value=30,
            max_value=60,
            value=45,
            step=5
        )
        
        hora_actual = datetime.now().hour
        minuto_actual = datetime.now().minute
        
        # ⏰ TEMPORIZADOR Y CAMBIO CADA 5 MINUTOS
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=300000, key="auto_refresh_5min")  # 300,000 ms = 5 minutos
        
        bloque_5min = (minuto_actual // 5) * 5
        st.sidebar.info(f"🕒 **Hora actual:** {hora_actual}:{minuto_actual:02d}\n"
                        f"🔄 **Próximo cambio automático en:** {bloque_5min + 5 - minuto_actual} minuto(s)")
        
        st.markdown("---")
        st.markdown("### 📊 Leyenda")
        st.markdown("""
        🟢 **Excelente** (≥ -55 dBm)  
        🟡 **Media** (-75 a -55 dBm)  
        🔴 **Mala** (-90 a -75 dBm)  
        ⬛ **Zona muerta** (< -90 dBm)
        """)
        
        st.markdown("---")
        st.markdown("**👥 Grupo No. 7**")
        st.markdown("NEXUS SDR-LINK")
        st.markdown("Líder: Daniel Felipe Escobar Ramirez.")
        st.markdown("👤 Integrante 1: [Daniel Andres Jara Olivera]")
        st.markdown("👤 Integrante 2: [Diana Carolina Leon Ocampo]")
    
    # ============================================
    # MAPA Y ESTADÍSTICAS
    # ============================================
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### 🗺️ Mapa de Cobertura")
        
        with st.spinner("Calculando zonas de emergencia..."):
            mapa = cobertura.generar_mapa(clima=clima, resolucion=resolucion)
            st_data = st_folium(mapa, width=700, height=500, key="mapa_emergencias_final")
    
    with col2:
        st.markdown("### 📊 Estadísticas")
        
        stats = cobertura.obtener_estadisticas(clima=clima)
        
        col_a, col_b = st.columns(2)
        
        with col_a:
            st.metric("📶 Promedio", f"{stats['potencia_promedio']:.1f} dBm")
            st.metric("🟢 Excelente", f"{stats['cobertura_excelente']:.1f}%")
            st.metric("🔴 Mala", f"{stats['cobertura_mala']:.1f}%")
        
        with col_b:
            st.metric("📈 Máxima", f"{stats['potencia_max']:.1f} dBm")
            st.metric("🟡 Media", f"{stats['cobertura_media']:.1f}%")
            st.metric("⬛ Zona muerta", f"{stats['zonas_muertas']:.1f}%")
        
        # Gráfico de barras
        fig, ax = plt.subplots(figsize=(6, 3))
        categorias = ['Excelente', 'Media', 'Mala', 'Zona muerta']
        valores = [
            stats['cobertura_excelente'],
            stats['cobertura_media'],
            stats['cobertura_mala'],
            stats['zonas_muertas']
        ]
        colores_bar = ['green', 'gold', 'red', 'gray']
        
        bars = ax.bar(categorias, valores, color=colores_bar, edgecolor='black', linewidth=1)
        ax.set_ylim(0, 100)
        ax.set_ylabel('Porcentaje (%)')
        ax.set_title('Distribución de Cobertura')
        
        for bar, val in zip(bars, valores):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2,
                   f'{val:.1f}%', ha='center', va='bottom', fontsize=9)
        
        plt.tight_layout()
        st.pyplot(fig)
    
    # ============================================
    # CAPTURA DEL MOMENTO (DOBLE ARCHIVO - DEFINITIVA)
    # ============================================
    st.markdown("---")
    st.markdown("### 📸 Captura del Momento (Anterior vs Reciente)")

    import json
    import os

    def generar_imagen_informe(titulo, fecha_mostrar, clima_mostrar, stats_mostrar):
        img = Image.new('RGB', (600, 400), color=(24, 24, 24))
        d = ImageDraw.Draw(img)
        blanco = (255, 255, 255)
        verde = (0, 255, 0)
        amarillo = (255, 255, 0)
        rojo = (255, 0, 0)

        d.text((20, 20), titulo, fill=blanco)
        d.text((20, 60), f"Fecha: {fecha_mostrar}", fill=blanco)
        d.text((20, 90), f"Clima actual: {clima_mostrar}", fill=blanco)
        d.text((20, 130), f"Potencia Promedio: {stats_mostrar['potencia_promedio']:.1f} dBm", fill=blanco)
        d.text((20, 160), f"Potencia Máxima: {stats_mostrar['potencia_max']:.1f} dBm", fill=blanco)
        d.text((20, 200), f"Cobertura Excelente: {stats_mostrar['cobertura_excelente']:.1f}%", fill=verde)
        d.text((20, 230), f"Cobertura Media: {stats_mostrar['cobertura_media']:.1f}%", fill=amarillo)
        d.text((20, 260), f"Cobertura Mala: {stats_mostrar['cobertura_mala']:.1f}%", fill=rojo)
        d.text((20, 290), f"Zonas Muertas: {stats_mostrar['zonas_muertas']:.1f}%", fill=(128, 128, 128))
        d.text((20, 340), "Grupo No. 7 - NEXUS SDR-LINK", fill=blanco)
        d.text((20, 370), "Líder: Daniel Felipe Escobar R.", fill=blanco)

        return img

    # ⏰ Calcular bloque de 5 minutos
    minuto_actual = datetime.now().minute
    bloque_actual = minuto_actual // 5

    # 📁 Archivos de guardado
    archivo_actual = "captura_actual.json"
    archivo_anterior = "captura_anterior.json"

    # 1. Leer lo que hay en el archivo "actual" (que será el "anterior" para esta ejecución)
    datos_previos = None
    if os.path.exists(archivo_actual):
        try:
            with open(archivo_actual, encoding='utf-8') as f:
                datos_previos = json.load(f)
        except:
            datos_previos = None

    # 2. Si en el archivo "actual" había datos de un bloque distinto, 
    #    los movemos al archivo "anterior" (para mostrarlos en la izquierda)
    if datos_previos is not None and datos_previos.get('bloque') != bloque_actual:
        with open(archivo_anterior, 'w', encoding='utf-8') as f:
            json.dump(datos_previos, f)

    # 3. Leer el archivo "anterior" para mostrar en la izquierda
    datos_anteriores = None
    if os.path.exists(archivo_anterior):
        try:
            with open(archivo_anterior, encoding='utf-8') as f:
                datos_anteriores = json.load(f)
        except:
            datos_anteriores = None

    # 4. Mostrar en dos columnas
    cap_col1, cap_col2 = st.columns(2)

    with cap_col1:
        st.markdown("#### 🕒 Captura Anterior")
        if datos_anteriores is not None and datos_anteriores.get('bloque') != bloque_actual:
            img_anterior = generar_imagen_informe(
                "NEXUS SDR-LINK - INFORME ANTERIOR",
                datos_anteriores['fecha'],
                datos_anteriores['clima'],
                datos_anteriores['stats']
            )
            st.image(img_anterior, use_container_width=True)
        else:
            st.info("Aún no hay datos anteriores. Esta es la primera carga.")

    with cap_col2:
        st.markdown("#### 🕐 Captura Reciente (Actual)")
        fecha_actual = datetime.now().strftime('%d/%m/%Y %H:%M')
        img_actual = generar_imagen_informe(
            "NEXUS SDR-LINK - INFORME RECIENTE",
            fecha_actual,
            clima,
            stats
        )
        st.image(img_actual, use_container_width=True)

        buf = BytesIO()
        img_actual.save(buf, format="PNG")
        byte_im = buf.getvalue()
        st.download_button(
            label="📥 Descargar Captura Reciente (PNG)",
            data=byte_im,
            file_name=f"captura_reciente_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
            mime="image/png"
        )

    # 5. Guardar los datos actuales en el archivo "actual" para el próximo ciclo
    datos_a_guardar = {
        "bloque": bloque_actual,
        "fecha": fecha_actual,
        "clima": clima,
        "stats": {
            "potencia_promedio": stats['potencia_promedio'],
            "potencia_max": stats['potencia_max'],
            "cobertura_excelente": stats['cobertura_excelente'],
            "cobertura_media": stats['cobertura_media'],
            "cobertura_mala": stats['cobertura_mala'],
            "zonas_muertas": stats['zonas_muertas']
        }
    }
    try:
        with open(archivo_actual, 'w', encoding='utf-8') as f:
            json.dump(datos_a_guardar, f)
    except Exception as e:
        pass
    
    # ============================================
    # QPSK
    # ============================================
    
    st.markdown("---")
    st.markdown("### 📡 Modulación QPSK")
    
    col3, col4 = st.columns(2)
    
    with col3:
        st.markdown("#### BER vs SNR")
        
        with st.spinner("Simulando..."):
            qpsk = SimuladorQPSK(1000)
            resultados = qpsk.simular()
            
            fig_ber = qpsk.graficar_ber(resultados)
            st.pyplot(fig_ber)
            
            if snr_qpsk in resultados['snr']:
                idx = resultados['snr'].index(snr_qpsk)
                ber_actual = resultados['ber'][idx]
                calidad = "✅ Excelente" if ber_actual < 1e-4 else "⚠️ Aceptable" if ber_actual < 1e-3 else "❌ Mala"
                st.info(f"**SNR={snr_qpsk} dB:** BER={ber_actual:.2e} - {calidad}")
    
    with col4:
        st.markdown("#### Constelación")
        
        fig_const = qpsk.graficar_constelacion(snr_qpsk)
        st.pyplot(fig_const)
        
        st.markdown("""
        **Interpretación:**
        - 🔵 Azul: Ideal
        - 🔴 Rojo: Con ruido
        - Menor dispersión = Mejor calidad
        """)
    
    # ============================================
    # PUNTOS DE INTERÉS
    # ============================================
    
    st.markdown("---")
    st.markdown("### 📍 Puntos de Interés")
    
    puntos = [
        (4.7115, -74.0715, "Centro"),
        (4.6605, -74.0895, "Sur"),
        (4.7705, -74.0495, "Norte"),
        (4.7205, -74.1395, "Occidente"),
        (4.7005, -74.0105, "Oriente"),
        (4.6705, -74.0995, "Bosa"),
        (4.7505, -74.0305, "Usaquén"),
        (4.6305, -74.0695, "Usme"),
        (4.6905, -74.1195, "Kennedy"),
        (4.7905, -74.0405, "Suba"),
    ]
    
    data = []
    for lat, lon, nombre in puntos:
        potencia = cobertura.calcular_intensidad_senal_con_tiempo(lat, lon, clima, minuto_actual)
        color, calidad, _ = cobertura.obtener_color_cobertura(potencia)
        emoji = {'green': '🟢', 'yellow': '🟡', 'red': '🔴', 'gray': '⬜'}[color]
        data.append({
            'Ubicación': f"{emoji} {nombre}",
            'Potencia (dBm)': f"{potencia:.1f}",
            'Calidad': calidad
        })
    
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    st.caption("📡 NEXUS SDR-LINK | Análisis en tiempo real | Bogotá, Colombia")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        st.stop()
