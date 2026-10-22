# Üzemeltetési útmutató

Ez a dokumentum a Raspberry Pi-n futó MQTT/Home Assistant szenzorküldők, a Gas mérőképfeldolgozás és az ezekhez tartozó segédparancsok beállítását írja le.

## Telepítés és verzióváltás

Friss, 32 bites, desktop nélküli Raspbian Lite telepítésen előfordulhat, hogy a pip nincs telepítve. A `python3 -m pip` parancsok használata előtt telepítsd:

```sh
sudo apt update && sudo apt install python3-pip -y
```

A `~/PROD` symlink a futtatandó checkout gyökerére mutasson. A célkönyvtárban közvetlenül legyen `ha/scripts`, például:

```text
/home/trenyik/ha/ha/scripts
```

A verzióváltó a checkout gyökerét kéri argumentumként:

```sh
~/ha/ha/scripts/switch_prod.sh "$HOME/ha"
```

A script telepítés előtt felsorolja a `PATH`-on megtalálható Python interpretereket verzióval együtt; ezek sorszámmal választhatók ki, de egyedi elérési út is megadható. Ha az `/etc/environment` még nem tartalmaz `PYTHON_BIN` értéket, a kiválasztott interpreter útvonalát ezután odaírja, és ugyanazzal telepíti a csomagot editable módban. Meglévő `PYTHON_BIN` esetén azt használja és nem írja felül. Ezután átállítja a `~/PROD` symlinket, és megkérdezi, hogy a négy systemd szolgáltatás közül melyeket telepítse: a folyamatos konyhai fényvezérlőt, az óránkénti Gas adatküldőt, a tízpercenkénti RPi konfigurációküldőt és/vagy a tízpercenkénti service-állapot küldőt. A választás szóközzel vagy vesszővel elválasztott lista lehet, például `1 3` vagy `1,3`; `0` esetén nem telepít systemd szolgáltatást. A telepítő nem módosít crontabot. Nem interaktív futtatásnál systemd szolgáltatást nem választ. A pip frissítés-ellenőrzése ki van kapcsolva; a `--break-system-packages` kapcsolót csak akkor adja át, ha a kiválasztott pip támogatja. Nem ír felül valódi fájlt vagy könyvtárat `~/PROD` helyén.

A szolgáltatások az `/etc/environment` `PYTHON_BIN` értékét használják, például:

```text
PYTHON_BIN=/usr/bin/python3.12
```

A shell wrapper-ek alapértelmezés szerint `python3`-at használnak. Futtatáskor másik interpreter is megadható a `PYTHON_BIN` környezeti változóval; értéke a Python teljes elérési útja legyen. Az útvonalat a `which` paranccsal kérdezheted le, például `which python3.14`:

```sh
which python3.14
PYTHON_BIN=/usr/local/bin/python3.14 ~/PROD/ha/scripts/rpi_psutils_send_data.sh
```

Az `/usr/local/bin/python3.14` csak példa: cseréld a `which python3.14` kimenetére. Ha a verzióváltó helyett másik interpreterrel kell telepíteni a csomagot, használd közvetlenül annak pipjét:

```sh
/usr/local/bin/python3.14 -m pip install -e "$HOME/ha" --break-system-packages
```

Ha nincs megadva, a wrapper-ek `python3`-at használnak. Az interpreter ellenőrzése:

```sh
python3 -c 'import sys; print(sys.executable)'
```

Az import tényleges forrásának ellenőrzése:

```sh
python3 -c 'import ha.utils.utils; print(ha.utils.utils.__file__)'
```

Ennek a `~/PROD/ha/utils/utils.py` fájlra kell mutatnia, nem egy korábbi checkoutra.

A `setup.py` deklarálja a `paho-mqtt` és `psutil` csomagokat. A Gas további függőségei: `google-cloud-vision`, Pillow, valamint a rendszerszintű ImageMagick és `rpicam-still`. A Gemini Interactions API-t használó OCR-függvényhez a `google-genai` legalább 2.3.0-s verziója szükséges. A `gas.py` fejlécében szereplő kompatibilis Vision telepítési parancs:

```sh
python3 -m pip install --break-system-packages \
  "google-cloud-vision==3.4.5" \
  "google-api-core<2.18" \
  "protobuf<4.21" \
  "grpcio<1.60"
sudo apt install -y imagemagick
```

Gemini OCR-hez telepítsd külön a Google GenAI SDK-t (`google-genai`); a `--prefer-binary` kapcsoló a rendelkezésre álló bináris csomagokat részesíti előnyben:

```sh
python3 -m pip install --prefer-binary "google-genai>=2.3.0"
```

A kamerás Gas képfeldolgozás Raspberry Pi-n fut; a `rpicam-still` parancsnak elérhetőnek kell lennie.

## MQTT-beállítások

A fő MQTT transport a következő környezeti változókat olvassa:

| Változó | Jelentés | Alapértelmezés |
| --- | --- | --- |
| `MQTT_BROKER` | MQTT broker címe | `1.1.1.1` (módosítsd a saját broker címére) |
| `MQTT_USERNAME` | MQTT felhasználónév | kódbeli alapérték; javasolt környezetből megadni |
| `MQTT_PASSWORD` | MQTT jelszó | kódbeli alapérték; javasolt környezetből megadni |

A fő `MQTT` osztály portja jelenleg rögzítetten `1883`; az `MQTT_PORT` változót a Gas és RPi küldők nem használják. A külön `dump_data.py` viszont olvassa az `MQTT_PORT`-ot.

Példa ideiglenes környezetbeállításra (valós értékeket adj meg; jelszót ne tegyél verziókezelésbe):

```sh
export MQTT_BROKER="192.168.1.10"
export MQTT_USERNAME="ha-publisher"
export MQTT_PASSWORD="<jelszó>"
```

A változók csak az adott shellből indított folyamatokra érvényesek. Cron esetén add meg őket a crontabban vagy egy jogosultságvédett, betöltött konfigurációban; a cron nem feltétlenül örökli az interaktív shell környezetét.

## Google Vision hitelesítés

A Gas OCR a Google Cloud Vision API-t használja. A kulcsfájl alapértelmezett helye:

```text
~/data/key.json
```

Ettől eltérő hely a `GOOGLE_APPLICATION_CREDENTIALS_PATH` változóval állítható be:

```sh
export GOOGLE_APPLICATION_CREDENTIALS_PATH="$HOME/keys/google-vision.json"
```

A `gas.py` ebből állítja be a Google könyvtár által használt `GOOGLE_APPLICATION_CREDENTIALS` változót. A kulcsfájl ne kerüljön a repositoryba vagy publikus HTTP könyvtárba. Nem Windows platformon a script a `GRPC_DNS_RESOLVER=native` beállítást is alkalmazza.

## Gemini API hitelesítés

A Gemini API-kulcsot a `GEMINI_API_KEY` környezeti változóban add meg. Ideiglenes, aktuális shellhez:

```sh
export GEMINI_API_KEY="<Gemini API-kulcs>"
```

Tartós, rendszer-szintű beállításhoz az `/etc/environment` fájlban `export` nélkül szerepeljen:

```text
GEMINI_API_KEY=<Gemini API-kulcs>
```

Cronból indított Gemini-feladathoz ellenőrizd, hogy a cronfolyamat megkapja-e ezt a változót; szükség esetén vedd fel a felhasználó crontabjába a futtatási sorok elé:

```cron
GEMINI_API_KEY=<Gemini API-kulcs>
```

A kulcs titkos adat: ne tedd verziókezelésbe, naplóba vagy publikus helyre.

## Futtatási parancsok

Közvetlen futtatás a projektgyökérből:

```sh
cd "$HOME/PROD"
python -m ha.scripts.rpi --send_data
python -m ha.scripts.gas --send_data
```

RPi CLI kapcsolók:

| Kapcsoló | Működés |
| --- | --- |
| `--send_config` | Home Assistant MQTT discovery konfigurációk küldése |
| `--send_data` | RPi statisztikák összegyűjtése és publikálása |
| `--dry_run` | `--send_data` mellett JSON kiírása stdout-ra publikálás helyett |
| `--model MODEL` | Modellnév felülírása az adott futásban |
| `--mac_address MAC` | MAC-cím felülírása az adott futásban |
| `--hostname HOST` | Hostnév felülírása az adott futásban |

Példák:

```sh
python -m ha.scripts.rpi --send_config --send_data
python -m ha.scripts.rpi --send_data --dry_run
python -m ha.scripts.rpi --send_config --model "Raspberry Pi test" --hostname test-rpi
```

## Fényvezérlő systemd service

A [ha-light-control-konyha.service](systemd/ha-light-control-konyha.service) a
`ha.apis.LIGHT` végtelen vezérlőciklusát futtatja. A systemd a folyamatot
normál kilépés vagy hiba után is 5 másodperccel újraindítja.

A service a `trenyik` felhasználó `~/PROD` symlinkjén keresztül indul, ezért a
verzióváltóval aktivált checkoutot futtatja. A Home Assistant hitelesítési
adatokat az `/etc/environment` fájlból tölti be; ne kerüljön token a unit
fájlba vagy a repositoryba:

```text
HA_LLA_TOKEN=<Home Assistant long-lived access token>
HA_REST_URL=http://<home-assistant-host>:8123/api
HA_REQUEST_TIMEOUT=10
```

Telepítés a Raspberry Pi-n:

```sh
sudo install -m 644 "$HOME/PROD/systemd/ha-light-control-konyha.service" \
  /etc/systemd/system/ha-light-control-konyha.service
sudo systemctl daemon-reload
sudo systemctl enable --now ha-light-control-konyha.service
```

Ellenőrzés és naplózás:

```sh
systemctl status ha-light-control-konyha.service
journalctl -u ha-light-control-konyha.service -f
```

Ha később módosítod a `PYTHON_BIN` értékét az `/etc/environment` fájlban, indítsd
újra a kiválasztott service-t vagy timert, hogy a systemd újra betöltse a
környezeti változót.

A unit fájlok abszolút `/home/trenyik/PROD` munkakönyvtárat használnak. Módosítás
után telepítsd újra az érintett unit fájlt, majd töltsd újra a systemd-t:

```sh
sudo install -m 644 "$HOME/PROD/systemd/ha-light-control-konyha.service" \
  /etc/systemd/system/ha-light-control-konyha.service
sudo systemctl daemon-reload
sudo systemctl restart ha-light-control-konyha.service
```

## Gas és RPi systemd feladatok

A `ha-gas-data.service` óránként egyszer futtatja a `gas.py --send_data`
parancsot. A `ha-rpi-data.service` tízpercenként futtatja a
`rpi.py --send_data` parancsot. Mindkettő egyszer fut le; az ismétlést a
hozzájuk tartozó systemd timer végzi. Sikertelen futás esetén a service egy
perc múlva próbálkozik újra. A kimenet a journalba kerül.

Mindkét service a `trenyik` felhasználóként, a `~/PROD` könyvtárból indul, és
az `/etc/environment` fájlból olvassa be a környezetet.

Telepítés és timerek engedélyezése a Raspberry Pi-n:

```sh
sudo install -m 644 "$HOME/PROD/systemd/ha-gas-data.service" \
  "$HOME/PROD/systemd/ha-gas-data.timer" \
  "$HOME/PROD/systemd/ha-rpi-data.service" \
  "$HOME/PROD/systemd/ha-rpi-data.timer" \
  /etc/systemd/system/
sudo systemctl daemon-reload
if systemctl list-unit-files --no-legend ha-rpi-config.timer \
  | grep -q '^ha-rpi-config\.timer'; then
  sudo systemctl disable --now ha-rpi-config.timer
fi
sudo systemctl enable --now ha-gas-data.timer ha-rpi-data.timer
```

Ellenőrzés és naplózás:

```sh
systemctl list-timers ha-gas-data.timer ha-rpi-data.timer
systemctl status ha-gas-data.service ha-rpi-data.service
journalctl -u ha-gas-data.service -u ha-rpi-data.service -f
```

## Service-állapotok küldése MQTT-re

A `ha.scripts.service` a `ha-light-control-konyha`, `ha-gas-data` és `ha-rpi-data` service-ek systemd `ActiveState` értékét küldi az `rpi/<hostname>_<MAC-cím>/systemctl` topicra, JSON-ként: `{"light": "active", "gas": "inactive", "rpi": "not-installed"}`. A `not-installed` azt jelenti, hogy a unit nincs telepítve. Emellett időbélyegeket is küld (ISO 8601, a Pi helyi időzónájával, például `2026-10-11T21:50:08+02:00`): a fényvezérlőnél az aktuális indítás idejét (`light_started`), a Gas és RPi feladatoknál a timer utolsó és következő futását (`gas_last_run`, `gas_next_run`, `rpi_last_run`, `rpi_next_run`); ha még nem volt futás, az érték `null`. A `--send_config` (vagy `--send-config`) minden értékhez egy Home Assistant szenzort ír le ugyanahhoz az eszközhöz, mint az `rpi.py`; a `--send_data` (vagy `--send-data`) az adatokat küldi, `--dry_run` mellett csak kiírja.

Az adatüzenet retained, és két nap után lejár a brokeren (MQTT v5 message expiry); a discovery konfiguráció nem jár le. Ehhez a brokernek támogatnia kell az MQTT v5-öt (Mosquitto 1.6 vagy újabb).

```sh
python -m ha.scripts.service --send_config --send_data --dry_run
```

A `ha-service-status.timer` tízpercenként futtatja a `--send_config --send_data` parancsot; a `switch_prod.sh` 4-es menüpontja telepíti.
### RPi MQTT topicok és adatok

Az RPi adatpublikálás topicja:

```text
rpi/<hostname>_<MAC-cím>/hardware
```

Például `hostname=raspberrypi` és a MAC-cím kettőspontok nélküli alakja esetén: `rpi/raspberrypi_AABBCCDDEEFF/hardware`. A `--hostname` és `--mac_address` kapcsoló futásonként felülírhatja az azonosítóban használt értékeket.

A `--send_data` a `Mypsutil.get_all_stat()` teljes eredményét JSON-ként küldi erre a topicra. A payload fő mezői:

| Mező | Tartalom |
| --- | --- |
| `cpu_freq` | CPU aktuális, minimum és maximum frekvenciája |
| `cpu_times_percent` | CPU időarányok: user, nice, system, idle és iowait (platformtól függően) |
| `cpu` | CPU hőmérsékletek és kihasználtság |
| `load` | 1, 5 és 15 perces, CPU-magokra normalizált load |
| `disk` | Gyökérfájlrendszer teljes, használt és szabad helye, százalékosan is |
| `memory` | RAM teljes, használt és elérhető mennyisége, százalékosan is |
| `net_io_counters` | Küldött és fogadott hálózati adatmennyiség MiB-ban; két mintavétel különbsége |
| `timestamp` | UTC időbélyeg |
| `containers` | Futó Docker konténerek száma, ha a Docker Python csomag telepített; egyébként üres objektum |
| `processes` | Legfeljebb öt, CPU-használat szerint kiválasztott folyamat |
| `sd_write_speed` | SD-kártya írási sebességének mérése |

A JSON-payload szerkezete sematikusan:

```text
{
  "cpu_freq": {"current": ..., "min": ..., "max": ...},
  "cpu_times_percent": {...},
  "cpu": {"temperature": {...}, "percent": ...},
  "load": {"last1min": ..., "last5min": ..., "last15min": ...},
  "disk": {...},
  "memory": {...},
  "net_io_counters": {"bytes_recv": ..., "bytes_sent": ...},
  "timestamp": "...",
  "containers": {...},
  "processes": [...],
  "sd_write_speed": {"total": ...}
}
```

A `--send_config` Home Assistant MQTT discovery konfigurációkat küld, szenzoronként a következő mintájú topicra:

```text
homeassistant/sensor/<hostname>_<MAC-cím>/<szenzor-azonosító>/config
```

A discovery által létrehozott RPi szenzorok a CPU-magok hőmérsékletei és kihasználtsága, lemez- és memóriaadatok, 1/5/15 perces load, valamint SD-írási sebesség. A data topic teljes payloadja ezen kívül frekvencia-, CPU-idő-, hálózati, folyamat-, konténer- és időbélyegadatokat is tartalmaz. A publikálás retained üzenetként történik.

Gas CLI kapcsolók:

| Kapcsoló | Működés |
| --- | --- |
| `--send_config` | Gas szenzorok discovery konfigurációinak küldése |
| `--send_data` | Mérőállás olvasása, statisztikák számítása és publikálása |
| `--dry_run` | `--send_data` mellett a statisztikák JSON kiírása MQTT adatpublikálás helyett |

A Gas dry-runnak is el kell érnie az MQTT brokert, mert a korábbi mérőállást onnan olvassa ki; az új adatot viszont nem publikálja.

## Shell wrapper-ek

A wrapper-ek a `~/PROD` symlinket használják, ezért verzióváltás után is az aktív checkoutból futnak. A normál kimenetet naplófájlba irányítják:

| Script | Funkció |
| --- | --- |
| `ha/scripts/rpi_psutils_send_config.sh` | RPi discovery konfigurációk |
| `ha/scripts/rpi_psutils_send_data.sh` | RPi adatok |
| `ha/scripts/rpi_psutils_send_data_and_config.sh` | RPi konfigurációk és adatok |
| `ha/scripts/rpi_psutils_send_data_dry_run.sh` | RPi JSON stdout-ra, MQTT adatküldés nélkül |
| `ha/scripts/rpi.sh` | Régi rövid RPi alias, adatküldés |
| `ha/scripts/gas_send_config.sh` | Gas discovery konfigurációk |
| `ha/scripts/gas_send_data.sh` | Gas mérés és publikálás |
| `ha/scripts/gas_send_data_and_config.sh` | Gas konfigurációk és mérés |
| `ha/scripts/gas_send_data_dry_run.sh` | Gas JSON stdout-ra, adatpublikálás nélkül |
| `ha/scripts/gas.sh` | Régi rövid Gas alias, adatküldés |

A dry-run wrapper-ek nem irányítják át az stdout-ot, így a JSON megjelenik a terminálban. A normál RPi és Gas logok a `~/PROD/ha/scripts/log_rpi.txt`, illetve `~/PROD/ha/scripts/log_gas.txt` fájlba kerülnek.
Az RPi szenzorok discovery konfigurációjának módosítása után futtasd egyszer a `~/PROD/ha/scripts/rpi_psutils_send_data_and_config.sh` scriptet; a tízpercenkénti cron csak adatot küld.

## Ütemezés crontabbal

A verzióváltó az RPi sort tízpercenkéntire állítja. Ha a Gas cron beállítására igennel válaszolsz, a Gas futás óránként a 15. percben történik:

```cron
PYTHON_BIN=/usr/bin/python3.14
*/10 * * * * /bin/bash "$HOME/PROD/ha/scripts/rpi_psutils_send_data.sh"
15 * * * * /bin/bash "$HOME/PROD/ha/scripts/gas_send_data.sh"
```

A crontabot a `crontab -e` paranccsal szerkesztheted; a `PYTHON_BIN` sort a futtatási sorok elé tedd, `export` nélkül. Cseréld le `/usr/bin/python3.14` értéket a `which python3.14` teljes elérési utat adó kimenetére. Ez a beállítás a sor alatti cron feladatokra érvényes. Ha a változót kihagyod, a scriptek alapértelmezés szerint `python3`-at használnak.

A beállítás felhasználónként különálló. A verzióváltót azon a felhasználón futtasd, amelyiknek a cronját módosítani szeretnéd; `sudo` nélkül. Ha a Gas kérdésre `N`-t vagy Entert válaszolsz, a telepítő a meglévő Gas cron bejegyzést változatlanul meghagyja.

Aktuális cron ellenőrzése:

```sh
crontab -l
```

## Gas képek

A Gas képfolyamata a következő:

1. A `rpicam-still` felvételt készít.
2. Az ImageMagick `convert` negatív képet ír a `/var/tmp/vision` könyvtárba.
3. A Python képmódosítása és kivágása után a végleges kép ugyanazon a fájlútvonalon marad.
4. A `latest.jpg` symlink az utoljára elkészült képre mutat.

A fájlok útvonala:

```text
/var/tmp/vision/<YYYY_MM_DD_HH_MM_SS>.jpg
/var/tmp/vision/latest.jpg -> /var/tmp/vision/<legutóbbi kép>.jpg
```

A link céljának ellenőrzése:

```sh
readlink -f /var/tmp/vision/latest.jpg
```

A könyvtár létrehozásához és napi takarításához a `gas.py` fejlécében dokumentált tmpfiles konfiguráció használható. A `USERNAME` helyére a Pi felhasználónevét kell írni:

```sh
sudo tee /etc/tmpfiles.d/vision.conf <<'EOF'
d /var/tmp/vision 0750 USERNAME USERNAME -
e /var/tmp/vision - - - 7d
EOF
```

A tényleges képkészítés csak Raspberry Pi kamerával futtatható. Kézi, előfeldolgozás nélküli OCR vizsgálatnál a `gas.py` `--send_data` helyett jelenleg nem ad külön image-only CLI opciót; az OCR metódus Pythonból `image_path` paraméterrel is meghívható.

## Képek HTTP-n keresztül

A `switch_prod.sh` futtatásakor válaszd az `5`-ös szolgáltatást. Ez telepíti és rendszerindításkor is elindítja a `ha-vision-http.service` systemd szolgáltatást, amely a `/var/tmp/vision` könyvtárat szolgálja ki a 8000-es porton.

A legutóbbi kép URL-je:

```text
http://<PI-IP-CÍME>:8000/latest.jpg
```

A szolgáltatás állapota, leállítása és naplója:

```sh
systemctl status ha-vision-http.service
sudo systemctl stop ha-vision-http.service
journalctl -u ha-vision-http.service -f
```

A beépített HTTP szerver nem biztosít hitelesítést. Csak megbízható helyi hálózaton használd, és ne szolgálj ki olyan könyvtárat, amely titkos kulcsokat vagy más érzékeny adatot tartalmaz.
