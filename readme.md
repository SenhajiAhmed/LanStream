# 📺 EGY-Stream

Application CLI en **Python orienté objet (OOP)** permettant de rechercher des films et séries, d'extraire automatiquement leurs flux HLS (`.m3u8`), et de lancer la lecture directement via le lecteur multimédia **MPV**.

Le projet inclut également un module de **sniffing avancé du trafic réseau (XHR/Fetch/Streams)** avec **Undetected ChromeDriver** et **Selenium-Wire** (navigation non-headless, contournement anti-bot et préservation de l'empreinte TLS).

---

## 🚀 Fonctionnalités

- 🔍 **Recherche interactive en ligne de commande** : Interroge le moteur de recherche et mappe automatiquement les titres arabes/anglais aux identifiants uniques de vidéos (`vid`).
- 🔢 **Sélection indexée par numéros** : Présente les résultats sous forme de liste numérotée claire et permet à l'utilisateur de choisir directement par son numéro.
- ⚡ **Extraction automatique de flux (Fast Extractor)** : Résout les iframes des hébergeurs vidéo (`1vid.xyz`, etc.) et décompresse le JavaScript obfusqué (Dean Edwards Packer) pour extraire instantanément le flux master HLS (`master.m3u8`).
- ▶️ **Lecture directe avec MPV** : Lance la lecture plein écran avec transmission automatique des en-têtes HTTP requis (`Referer`).
- 🕵️ **Suite de tests & Sniffer XHR (`tests/test_sniff.py`)** : Outil d'analyse pour inspecter les requêtes HTTP/HTTPS, capturer le DOM HTML et détecter les flux vidéo en direct.
- 📂 **Dossier `output/` dédié** : Centralise tous les exports JSON, dumps HTML et historiques de requêtes.

---

## 📂 Architecture du Projet

```text
EGY-Stream/
├── main.py                     # Point d'entrée de l'application CLI (EgyStreamApp)
├── config.py                   # Configuration globale (URLs, en-têtes, timeouts)
├── requirements.txt            # Dépendances du projet
├── readme.md                   # Documentation complète
├── .gitignore
├── models/
│   ├── __init__.py
│   └── video.py                # Modèle de données Video (ID, titre, URL page, flux)
├── services/
│   ├── __init__.py
│   ├── search_service.py       # Recherche & mapping des vidéos par nom
│   ├── extractor_service.py    # Déobfuscation & extraction du flux .m3u8
│   ├── player_service.py       # Contrôleur de lecture via MPV
│   └── stream_proxy_service.py # Micro-Proxy HTTP/HLS local pour partage Wi-Fi (Option A)
├── utils/
│   ├── __init__.py
│   ├── logger.py               # Logger formaté
│   └── ui.py                   # Interface terminal (bannières, couleurs, menus numérotés)
├── tests/
│   ├── __init__.py
│   ├── test_extractor.py       # Tests unitaires de recherche et d'extraction
│   ├── test_proxy.py           # Tests unitaires du micro-proxy LAN
│   └── test_sniff.py           # Outil de sniffing réseau (Undetected Chrome / Selenium-Wire)
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

---

## 📥 Installation

1. Clonez ce dépôt et rendez-vous dans le dossier :
   ```bash
   git clone https://github.com/SenhajiAhmed/EGY-Stream.git
   cd EGY-Stream
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