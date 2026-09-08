# 📺 LanStream

Application CLI moderne en **Python orienté objet (OOP)** permettant de rechercher des films et séries sur plusieurs catalogues (**Cineby / TMDB** & **Egy-Stream**), de choisir la résolution désirée (4K HDR, 1080p, 720p, 360p, Auto), d'extraire automatiquement leurs flux HLS/fMP4 déprotégés, et de les visionner :
- En **local** via le lecteur haute-performance **MPV**
- En **streaming Wi-Fi local** via un micro-proxy intégré compatible avec tous vos appareils (PC, smartphones, iPhone/Android, et **Smart TV Samsung / Tizen / Orsay**).

Le projet inclut également un module de **sniffing réseau headless** ultra-rapide avec détection précoce (early-exit) et interception CDP.

---

## 🚀 Fonctionnalités

- 🌐 **Recherche multi-sources agrégée** : Recherche instantanée simultanée sur le catalogue international **Cineby** (via TMDB avec notes ⭐ et dates) et sur le catalogue arabe **Egy-Stream**.
- 🔢 **Sélection indexée par numéros** : Présente les résultats sous forme de liste numérotée claire (`[cineby]`, `[egy-stream]`) pour un choix rapide au clavier.
- 📺 **Sélecteur de résolutions interactif** : Détecte les profils disponibles dans les flux HLS master et permet de choisir entre **Auto**, **4K Ultra HD**, **1080p Full HD**, **720p HD**, ou **360p**.
- ⚡ **Extraction automatique & Headless Sniffer** : Détecte et extrait les flux master HLS (`master.m3u8`) et fMP4 en quelques secondes via Chrome CDP sans navigation visible.
- ▶️ **Lecture directe avec MPV** : Lance la lecture plein écran avec transmission automatique des en-têtes HTTP requis (`Referer`, `Origin`) et sélection automatique de la résolution (`--vid`).
- 📡 **Micro-Proxy Wi-Fi & Smart TV** :
  - **Lecteur Web HTML5 universel** : `http://<IP_LOCALE>:8080/` avec `Hls.js` et détection intelligente.
  - **Flux Direct MP4 Rémuxé à la volée (`/stream.mp4`)** : Idéal pour les anciennes Smart TV (Samsung Série 3-5 Orsay / NetRange) sans transcodage CPU (`-c copy`).
  - **URL Directe M3U8 (`/playlist.m3u8`)** : Réécrite à chaud pour VLC ou lecteurs IPTV.
- 📝 **Audit & Diagnostic Réseau en temps réel** : Détection automatique des appareils connectés sur le Wi-Fi (Smart TV, mobile, PC), journalisation des transferts et télémétrie des erreurs.

---

## 📂 Architecture du Projet

```text
LanStream/
├── main.py                     # Point d'entrée de l'application CLI (LanStreamApp)
├── config.py                   # Configuration globale (URLs, en-têtes, timeouts)
├── requirements.txt            # Dépendances du projet
├── readme.md                   # Documentation complète
├── .gitignore
├── models/
│   ├── __init__.py
│   └── video.py                # Modèle de données Video (ID, titre, provider, résolutions)
├── services/
│   ├── __init__.py
│   ├── search_service.py       # Recherche multi-sources (TMDB/Cineby + Egy-Stream)
│   ├── extractor_service.py    # Déobfuscation, sniffer headless CDP & parseur de résolutions
│   ├── player_service.py       # Contrôleur de lecture via MPV avec sélection de piste vidéo
│   ├── stream_proxy_service.py # Micro-Proxy HTTP/HLS local pour partage Wi-Fi & Smart TV
│   └── device_logger_service.py# Suivi et audit télémétrique des appareils connectés
├── utils/
│   ├── __init__.py
│   ├── logger.py               # Logger formaté
│   └── ui.py                   # Interface terminal (bannières, couleurs, menus numérotés)
├── tests/
│   ├── __init__.py
│   ├── test_extractor.py       # Tests unitaires de recherche et d'extraction
│   ├── test_proxy.py           # Tests unitaires du micro-proxy LAN et réécriture fMP4
│   └── test_sniff.py           # Outil de sniffing réseau autonome
└── output/
    └── .gitkeep                # Répertoire de stockage des fichiers générés
```

---

## ⚙️ Prérequis

1. **Python 3.9+** (testé et compatible avec Python 3.13)
2. **Lecteur MPV** installé et accessible dans le `PATH` :
   - **Fedora** : `sudo dnf install mpv`
   - **Ubuntu / Debian** : `sudo apt install mpv`
   - **Arch Linux** : `sudo pacman -S mpv`
   - **macOS** : `brew install mpv`
3. **FFmpeg** (requis pour le mode Direct MP4 / Smart TV) :
   - `sudo apt install ffmpeg` ou `sudo dnf install ffmpeg`

---

## 📥 Installation

1. Clonez ce dépôt et rendez-vous dans le dossier :
   ```bash
   git clone https://github.com/SenhajiAhmed/LanStream.git
   cd LanStream
   ```

2. Créez et activez un environnement virtuel :
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Installez les dépendances :
   ```bash
   pip install -r requirements.txt
   ```

---

## 🎮 Utilisation

### 1. Mode Interactif Principal
Lancez l'application :
```bash
python main.py
```

**Déroulement :**
1. Saisissez votre mot-clé de recherche (ex: `حرامية في كي جي تو`).
2. Les résultats trouvés s'affichent numérotés (1, 2, 3...).
3. Entrez simplement le numéro du film choisi.
4. L'application extrait le flux et vous propose 3 modes d'action :
   - `1` : ▶️ **Lecture locale avec MPV**
   - `2` : 📡 **Partage Wi-Fi (Option A)** : démarre le micro-proxy HTTP local et affiche l'URL du lecteur web pour les smartphones / Smart TV.
   - `3` : 🚀 **Lecture locale MPV + Partage Wi-Fi simultané**
   - `4` : 🔙 Retour à la liste

### 2. Partage Wi-Fi Local (Micro-Proxy Multi-Appareils & Smart TV)
Lors de l'activation du relai Wi-Fi, l'application génère automatiquement :
- **Un Lecteur Web HTML5 universel** : `http://192.168.1.XX:8080/`
  Accessible depuis n'importe quel smartphone (iPhone/Android), tablette ou TV connectée via navigateur. Intègre un sélecteur de mode en 1 clic :
  - **Mode TV Samsung (Direct MP4)** : Pour téléviseurs anciens ou navigateurs sans MSE.
  - **Mode HLS** : Pour navigateurs modernes et appareils mobiles récents.
- **Un Flux Direct MP4 Déchiffré (Recommandé TV Samsung Série 3)** : `http://192.168.1.XX:8080/stream.mp4`
  Rémuxe le flux à la volée avec FFmpeg (`-c copy` à 0% CPU) et retire le chiffrement AES-128 côté hôte. Jouable immédiatement par le lecteur matériel natif des anciennes Smart TV (Samsung Orsay, NetRange, etc.).
- **Une URL directe M3U8 sans restrictions** : `http://192.168.1.XX:8080/playlist.m3u8`
  Compatible directement avec VLC (Média > Ouvrir un flux réseau) ou les applications IPTV.

### 3. Recherche Directe via Argument CLI
Vous pouvez directement passer la requête en paramètre :
```bash
python main.py -q "حرامية"
```

### 4. Mode Debug
Pour afficher les détails techniques des requêtes et de l'extraction :
```bash
python main.py --debug
```

---

## 📺 Le Défi du Streaming sur Smart TV : Problèmes & Solutions Architecturales

Diffuser un flux vidéo moderne vers un téléviseur connecté (notamment les **anciennes Smart TV Samsung Série 3-5 / Orsay / Tizen ancien**, ou tout téléviseur avec un navigateur WebKit limité) pose des défis techniques majeurs que les lecteurs web et proxies classiques ne peuvent pas surmonter directement.

Voici l'analyse détaillée des problèmes rencontrés et des solutions d'ingénierie implémentées dans **LanStream**.

---

### 1. ⚠️ Les Problèmes Rencontrés sur Smart TV

| Problème | Symptôme / Erreur | Cause Technique |
| :--- | :--- | :--- |
| **Masquage CDN & Faux MIME Type** | `networkError: fragLoadError`<br>`audioTrackLoadError` | Certains CDN (notamment MovieBox / Cineby) déguisent leurs fragments fMP4 avec des extensions `.html` et renvoient un en-tête `Content-Type: text/html; charset=utf-8`. Les moteurs TV et Hls.js rejettent immédiatement ces segments. |
| **Balises fMP4 relatives ignorées** | `HTTP 404 Not Found`<br>sur `/video_init.html` ou `/audio.m3u8` | Les balises d'initialisation fMP4 (`#EXT-X-MAP:URI="..."`) et de pistes audio (`#EXT-X-MEDIA:TYPE=AUDIO,...,URI="..."`) contenaient des chemins relatifs non résolus par les proxies basiques. |
| **Collision Multi-Pistes FFmpeg** | `BrokenPipeError: bytes_streamed: 65536`<br>`MEDIA_ERR_SRC_NOT_SUPPORTED` | Sur les films multi-langues et multi-résolutions (ex: *Titanic*), un mapping FFmpeg cumulatif (`-map 0:p:...` + `-map 0:v:...`) injectait **2 flux vidéo** et **5 flux audio** simultanément dans le MP4. Les puces matérielles TV crachaient dès le 1er bloc de 64 KB. |
| **Incompatibilité Codec 4K HEVC** | Écran noir / Image figée / Son seul | Les masters 4K proposent du HEVC/H.265 (Program 0). Les puces vidéo des téléviseurs de génération précédente ne décodent matériellement que le H.264 (AVC) jusqu'à 1080p. |
| **Restrictions CORS & Chiffrement AES-128** | Échec de lecture / Erreur DRM | Les requêtes vers les clés AES-128 (`#EXT-X-KEY`) et segments tiers sont bloquées par les règles de sécurité réseau strictes du navigateur TV. |

---

### 2. 🛠️ Les Solutions Déployées dans LanStream

```text
                                       ┌─────────────────────────────────────────────────────────┐
                                       │                   LanStream Micro-Proxy                 │
                                       │                                                         │
  ┌──────────────────────┐             │   1. Détection intelligente des balises (#EXT-X-MAP/KEY)│
  │     Upstream CDN     │             │   2. Sanitisation MIME Type (text/html ➔ video/mp4)     │
  │  (fMP4, AES-128,     │ ──────────► │   3. Filtrage dynamique par résolution choisie          │
  │   Segments obfusqués)│             │   4. Rémuxage FFmpeg strict (1 vidéo + 1 audio)         │
  └──────────────────────┘             └────────────────────────────┬────────────────────────────┘
                                                                    │
                                    ┌───────────────────────────────┴────────────────────────────┐
                                    ▼                                                            ▼
                     ┌─────────────────────────────┐                              ┌─────────────────────────────┐
                     │   Lecteur Web / Hls.js      │                              │  Samsung Smart TV (Orsay)   │
                     │   Auto-guérison & HLS Natif │                              │  Direct MP4 unifié (0% CPU) │
                     └─────────────────────────────┘                              └─────────────────────────────┘
```

#### A. Moteur de Réécriture Approfondie des Balises HLS
Le micro-proxy ne se contente pas de relayer les URLs de segments : il inspecte et réécrit **toutes les balises d'attributs `URI="..."`** de la norme HLS :
```text
Flux distant (Relatif)                           Flux réécrit par LanStream (Absolu & Proxifié)
────────────────────────────────────────────────────────────────────────────────────────────
#EXT-X-MAP:URI="video_360p_init.html"      ──►   #EXT-X-MAP:URI="http://192.168.1.X:8080/proxy?url=https%3A%2F%2F...init.html"
#EXT-X-MEDIA:TYPE=AUDIO,URI="audio_1.m3u8" ──►   #EXT-X-MEDIA:TYPE=AUDIO,URI="http://192.168.1.X:8080/proxy?url=https%3A%2F%2F...audio_1.m3u8"
#EXT-X-KEY:METHOD=AES-128,URI="key.key"    ──►   #EXT-X-KEY:METHOD=AES-128,URI="http://192.168.1.X:8080/proxy?url=https%3A%2F%2F...key.key"
```
Résultat : les fichiers d'init fMP4 et les playlists audio séparées sont servis de manière transparente sans aucune erreur 404.

#### B. Sanitisation Automatique des Types MIME
Le composant `_proxy_upstream` inspecte la nature des flux et remplace dynamiquement les faux en-têtes `text/html` par les véritables types MIME attendus par les décodeurs :
- Fragments vidéo fMP4 / TS : `video/mp4` ou `video/mp2t`
- Pistes audio fMP4 : `audio/mp4`
- Sous-titres : `text/vtt`
- Clés AES-128 : `application/octet-stream` avec mise en cache mémoire RAM instantanée.

#### C. Remuxing FFmpeg Haute-Précision à Flux Unique (`/stream.mp4`)
Pour les téléviseurs dépourvus de support MSE moderne, `/stream.mp4` effectue un remuxing pass-through (`-c:v copy -c:a copy` à 0% de charge CPU) avec isolation stricte :
```python
# Sélection stricte d'UN SEUL flux vidéo et d'UN SEUL flux audio
if getattr(self.video, "selected_vid", None):
    prog_idx = self.video.selected_vid - 1
    cmd.extend(["-map", f"0:p:{prog_idx}:v:0", "-map", "0:a:0?"])
elif getattr(self.video, "available_resolutions", None):
    # Auto : Sélection intelligente du flux 1080p H.264 (ou 1er disponible)
    cmd.extend(["-map", f"0:p:{prog_1080p}:v:0", "-map", "0:a:0?"])
else:
    cmd.extend(["-map", "0:v:0", "-map", "0:a:0?"])
```
Le conteneur MP4 transmis au téléviseur ne contient **qu'une seule piste vidéo fluide et une seule piste audio**, éliminant instantanément toute fermeture de socket (`BrokenPipeError` à 64 KB) et assurant un démarrage immédiat.

#### D. Filtrage Dynamique de la Playlist Maître par Résolution
Lorsque l'utilisateur sélectionne une résolution (ex: `360p` ou `1080p`), `/playlist.m3u8` isole fidèlement le variant choisi tout en reliant la piste audio appropriée :
- Aucun gaspillage de bande passante.
- Prévention du basculement automatique forcé vers du 4K HEVC non supporté par la TV.

#### E. Télémétrie Côté Client & Auto-Guérison
Le lecteur HTML5 embarqué intègre une logique d'auto-récupération d'erreurs :
- `Hls.ErrorTypes.MEDIA_ERROR` ➔ Déclenche automatiquement `currentHls.recoverMediaError()`
- `Hls.ErrorTypes.NETWORK_ERROR` ➔ Déclenche automatiquement `currentHls.startLoad()`
- Échec irrémédiable ➔ Bascule silencieuse et transparente vers le mode matériel natif.
- Chaque incident est consigné en temps réel dans la console hôte et dans `output/devices_activity.log` via l'API interne `POST /api/log`.

---

## 🧪 Tests & Analyse Réseau (XHR Sniffing)

Le dossier `tests/` contient les outils de test et d'analyse :

### Test Unitaire Automatique
Vérifie la recherche et l'extraction sans lancer de lecteur :
```bash
python -m unittest tests/test_extractor.py
```

### Outil de Sniffing Réseau Avancé (`tests/test_sniff.py`)
Permet d'ouvrir un navigateur réel (Google Chrome non-headless avec Undetected ChromeDriver) pour analyser en profondeur les requêtes XHR et les flux vidéo protégés :
```bash
python tests/test_sniff.py --url "https://yam.ahwaktv.net/see.php?vid=f8ba4b0ce" --timeout 30
```
- **Résultats générés dans `output/`** :
  - `output/captured_page.html` : DOM HTML complet.
  - `output/captured_requests.json` : Journal structuré de toutes les requêtes/réponses réseau.
  - `output/detected_streams.txt` : Liste des flux vidéo et iframes détectés.

---

## 📝 Audit & Diagnostic des Appareils Connectés

Le système intègre un logger haute-précision pour suivre en direct et archiver de façon persistante tous les appareils accédant au flux (Smart TV, mobiles, PC, VLC) :

### 1. Fichiers de Logs Sauvegardés dans `output/` :
- **`output/devices_activity.log`** : Journal chronologique complet enregistrant chaque requête, IP cliente, port, type d'appareil, volume de données streamé et déconnexion inattendue.
- **`output/connected_devices.json`** : Registre structuré JSON recensant chaque appareil avec son profil complet (`ip`, `device_type`, `user_agent`, `total_requests`, `bytes_sent`, `errors_count` et l'historique détaillé de chaque erreur rencontrée).
- **`output/app.log`** : Journal d'exécution global de l'application (recherche, résolveurs, MPV et proxy).

### 2. Alertes en Temps Réel en Console :
- **Nouveau périphérique détecté** : Détecte automatiquement la marque et l'OS de l'appareil (ex : `Samsung Smart TV (Orsay / Série 3-5 ancienne)`).
- **Détection d'anomalies serveur** : Alerte immédiate avec détails si un appareil coupe la connexion (`ConnectionResetError`, `BrokenPipeError`).
- **Télémétrie d'erreurs côté client (TV / Navigateur)** : Le lecteur HTML5 rapporte automatiquement les erreurs internes du téléviseur (ex : `MEDIA_ERR_SRC_NOT_SUPPORTED`, erreurs de tampon HLS) via `POST /api/log`.

---

## 🛠️ Configuration (`config.py`)

Les paramètres peuvent être ajustés dans `config.py` :
- `BASE_URL` : URL de base du fournisseur (défaut : `https://yam.ahwaktv.net`).
- `DEFAULT_HEADERS` : En-têtes HTTP utilisés pour les requêtes.
- `OUTPUT_DIR` : Répertoire de sortie des résultats (`output/`).
- `MPV_BINARY` : Nom ou chemin de l'exécutable MPV.
- `REQUEST_TIMEOUT` : Délai d'expiration des requêtes HTTP (en secondes).

---

## 📄 Licence
Ce projet est distribué sous licence MIT.