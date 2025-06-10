# 3D STUDIO – Python / PyQt5 / OpenGL Tabanlı 3B Modelleme ve Görselleştirme Aracı

Bu depodaki kodlar, tıbbi görüntü yığınlarından (PNG dilimleri) veya mevcut OBJ geometri dosyalarından interaktif 3B mesh / nokta bulutu üretebilen, bunları detaylı olarak düzenlemenize olanak tanıyan, tamamen Python ile yazılmış platform-bağımsız bir masaüstü uygulamasıdır.

## İÇİNDEKİLER

1. [Özellikler](#1-özellikler)
2. [Sistem Gereksinimleri](#2-sistem-gereksinimleri)
3. [Gerekli Python Kütüphaneleri](#3-gerekli-python-kütüphaneleri)
4. [Hızlı Kurulum Adımları](#4-hızlı-kurulum-adımları)
5. [Uygulamayı Çalıştırma](#5-uygulamayı-çalıştırma)
6. [Detaylı Kullanım Kılavuzu](#6-detaylı-kullanım-kılavuzu)
7. [Proje Dizini ve Önemli Modüller](#7-proje-dizini-ve-önemli-modüller)
8. [Büyük Hacim & GPU İpuçları](#8-büyük-hacim--gpu-ipuçları)
9. [Sık Karşılaşılan Sorunlar](#9-sık-karşılaşılan-sorunlar)

# 1. ÖZELLİKLER

### Dilimsiz (slice) → Mesh/Nokta Bulutu Dönüşümü
- Tek seferde yüzlerce PNG dilimini okuyup marching-cubes algoritmasıyla renkli yüzey (mesh) oluşturur veya seyreltilmiş nokta bulutu üretir.
- Otomatik (Otsu) veya manuel eşik seçimi, Gauss / Medyan / Bilateral gürültü azaltma seçenekleri.

### OBJ Yükleme ve Çoklu Materyal Desteği
- Tek dosyada birden fazla usemtl bölümü içeren OBJ'leri hızlı yükler,
- MTL dosyasındaki Kd (diffuse) renklerini korur.

### Etkileşimli Düzenleme
- Taşı (Move), Döndür (Rotate), Ölçekle (Resize) araçları — hassasiyet kaydırıcılarıyla.
- Mesh kesme (Cut) aracı: Ekranda çizdiğiniz kırmızı çizgiye dik düzlemle modeli ikiye böler.
- Silgi (Erase) aracı: Ekranda dairesel fırçayla üçgenleri veya nokta bulutu noktalarını siler.

### Gelişmiş Görsel Yardımlar
- Sonsuz grid (XY / XZ / YZ veya hepsi), görünür eksen, ışıklandırılmış shader veya eski sabit-pipeline fallback'i.
- Inspector paneli: Seçili objenin konum / rotasyon / ölçek değerlerini canlı düzenleyin, üçgen & nokta sayısını görün.
- Undo / Redo (Hızlı Tekrar Butonlu), proje kaydet/aç, tema (light/dark) vb.

# 2. SİSTEM GEREKSİNİMLERİ

- **İşletim Sistemi:** Windows 10/11, macOS 12+, Linux (glibc ≥ 2.31)
- **Python:** 3.9 – 3.12 (CPython x64)
- **Ekran Kartı:** OpenGL 2.1 veya üstü destekleyen GPU (NVIDIA / AMD / Intel)
- **RAM:** Dilim boyutuna göre 8 GB+ önerilir (≥ 256×256×512 hacim ≈ 32 M voxel)
- **(İsteğe Bağlı)** CUDA 11+ için NVIDIA sürücüsü – torch & torchmcubes hızlandırma

# 3. GEREKLİ PYTHON KÜTÜPHANELERİ

Standart bir requirements.txt (basic, GPU'suz) içeriği:

```txt
PyQt5>=5.15.9
PyOpenGL>=3.1.6
numpy>=1.26
opencv-python>=4.10
scikit-image>=0.23
numba>=0.59
```

GPU destekli kullanmak isteyenler ek olarak:

```txt
torch>=2.2     (uyumlu CUDA tekeri)
torchmcubes>=0.1.1
```

**Ek Notlar**
- PyOpenGL-accelerate paketi %30'a kadar hız kazandırır (opsiyonel).
- Linux'ta Qt5 dev paketleri (örn. qtbase5-dev) gerekebilir.
- Numba Windows'ta "Build Tools for Visual C++ 14" ister.

# 4. HIZLI KURULUM ADIMLARI

```bash
# 1) Repoyu klonla
git clone https://github.com/kullanici/3d-studio.git
cd 3d-studio

# 2) Sanal ortam (önerilir)
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate

# 3) Kütüphaneleri yükle
pip install -r requirements.txt
# 3-b) GPU desteği isteniyorsa
pip install torch torchmcubes

# 4) Uygulamayı çalıştır
python main.py
```

# 5. UYGULAMAYI ÇALIŞTIRMA

```bash
(venv) python main.py
```

İlk çalıştırmada "3D Studio" ana penceresi Giriş Ekranı ile açılır.

# 6. DETAYLI KULLANIM KILAVUZU

### 6.1 Giriş Ekranı
- **OBJ Yükle** → dosyayı seç, sahneye eklenir; materyal renkleri korunur.
- **Obje Oluştur** → PNG dilim klasörü seç, Model Tipi (Mesh / Nokta Bulutu) vb. parametreleri ayarla, oluşturulan .obj otomatik sahneye yüklenir.

### 6.2 Ana Ekran & Araç Çubuğu

| Simge | Araç | Kısa Açıklama |
|-------|------|---------------|
| 🖰 | Cursor | Seçim. Sol tık = select, Ctrl = çoklu seçim |
| 🔄 | Rotate | Seçili mesh'i döndür; Alt+Sağ = kamerayı döndür |
| ↔️ | Move | X/Y/Z taşı |
| 📏 | Resize | Uniform ölçek; Shift+fare = zoom |
| 🩹 | Erase | Fırça ile üçgen/nokta sil; Sağ tık = Undo |
| ✂️ | Cut | Çizgiye dik düzlemle kes |
| 🗑️ | Objeyi Sil | Mesh'i sahneden kaldır |
| 🌈 | Background Renk | Arka plan |
| ↶/↷ | Undo / Redo | Hızlı geri/ileri |
| ➕ | Add Object | Yeni OBJ ekle |
| 🏠 | Giriş Ekranı | Ana menüye dön |

### 6.3 Sağ Paneller
- **Objeler ▾** – Sahnedeki tüm mesh'ler
- **Inspector ▾** – Konum / Rotasyon / Ölçek ve üçgen/nokta sayısı
- **Notlar ▾** – Proje notları (scene.json içine kaydedilir)

### 6.4 Menü Çubuğu
- **Dosya** → Yeni / Oluştur / Aç / Kaydet / Kapat
- **Ayarlar** → Tema, Eksen Göster, Grid, Nokta Boyutu, GPU vb.

# 7. PROJE DİZİNİ & ÖNEMLİ MODÜLLER

```
main.py                 – QApplication başlangıcı
main_window.py          – Pencere & proje yönetimi
entry_screen.py         – Dilimden model üretme sihirbazı
main_screen.py          – Sahne + paneller
cube_3d_widget.py       – OpenGL çizim & etkileşim
mesh.py                 – Mesh veri yapısı (Numba hızlandırmalı)
volume_loader.py        – PNG dilim yükleyici (çok iş parçacıklı)
surface_extractor.py    – Marching-cubes + smoothing
point_cloud_extractor.py– Voxel → nokta bulutu örnekleme
shader_utils.py         – GLSL yardımcıları
...
```

# 8. BÜYÜK HACİM & GPU İPUÇLARI

- 32 M+ voxel hacimlerde stream_extract_surface RAM'i düşürür.
- NVIDIA GPU + torchmcubes → marching-cubes 10–20× hızlanır.
- Nokta bulutu silgi/clip işlemleri CPU'da, numba JIT ile.

# 9. SIK KARŞILAŞILAN SORUNLAR

- **QOpenGLWidget siyah geliyor** → GPU OpenGL 2.1 desteklemiyor / sürücü eski.
- **ImportError: DLL load failed: libGL** → Windows'ta mesa-opengl eksik;  
  `pip install PyOpenGL-accelerate` veya tam GPU sürücü kurulumu.
- **torch + CUDA sürüm uyuşmaz** →  
  `pip uninstall torch && pip install torch==<uyumlu-sürüm+cu118>` (bkz. PyTorch tablosu). 