# Üzemeltetési útmutató

Ez a dokumentum a Raspberry Pi-n futó MQTT/Home Assistant szenzorküldők, a Gas mérőképfeldolgozás és az ezekhez tartozó segédparancsok beállítását írja le.

## Telepítés és verzióváltás

A `~/PROD` symlink a futtatandó checkout gyökerére mutasson. A célkönyvtárban közvetlenül legyen `ha/scripts`, például:

```text
/home/trenyik/ha/ha/scripts
```

A verzióváltó a checkout gyökerét kéri argumentumként:

```sh
~/ha/ha/scripts/switch_prod.sh "$HOME/ha"
```

A script editable módban telepíti a csomagot (`python3 -m pip install -e . --break-system-packages`), átállítja a `~/PROD` symlinket, frissíti az RPi cron sort, és interaktív futtatáskor rákérdez a Gas cron felvételére. Nem ír felül valódi fájlt vagy könyvtárat `~/PROD` helyén.

A normál wrapper-ek `python` parancsot használnak, a verzióváltó jelenleg `python3`-at. Ezeknek ugyanarra a Python interpreterre kell mutatniuk, különben a wrapper egy régi editable telepítést tölthet be. Ellenőrzés:

```sh
python -c 'import sys; print(sys.executable)'
python3 -c 'import sys; print(sys.executable)'
```

Ha eltérnek, telepítsd a checkoutot a wrapper által használt interpreterrel:

```sh
cd "$HOME/PROD"
python -m pip install -e . --break-system-packages
```

Az import tényleges forrásának ellenőrzése:

```sh
python -c 'import ha.utils.utils; print(ha.utils.utils.__file__)'
```

Ennek a `~/PROD/ha/utils/utils.py` fájlra kell mutatnia, nem egy korábbi checkoutra.

A `setup.py` deklarálja a `paho-mqtt` és `psutil` csomagokat. A Gas további függőségei: `google-cloud-vision`, Pillow, valamint a rendszerszintű ImageMagick és `rpicam-still`. A `gas.py` fejlécében szereplő kompatibilis Vision telepítési parancs:

```sh
python3 -m pip install --break-system-packages \
  "google-cloud-vision==3.4.5" \
  "google-api-core<2.18" \
  "protobuf<4.21" \
  "grpcio<1.60"
sudo apt install -y imagemagick
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

## Ütemezés crontabbal

A verzióváltó az RPi sort tízpercenkéntire állítja. Ha a Gas cron beállítására igennel válaszolsz, a Gas futás óránként a 15. percben történik:

```cron
*/10 * * * * /bin/bash "$HOME/PROD/ha/scripts/rpi_psutils_send_data.sh"
15 * * * * /bin/bash "$HOME/PROD/ha/scripts/gas_send_data.sh"
```

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

A képek ideiglenes megosztásához indítsd a Python HTTP szervert a Pi-n:

```sh
nohup python3 -m http.server 8000 \
  --bind 0.0.0.0 \
  --directory /var/tmp/vision \
  > "$HOME/vision-http-server.log" 2>&1 &
echo $! > "$HOME/vision-http-server.pid"
```

A legutóbbi kép URL-je:

```text
http://<PI-IP-CÍME>:8000/latest.jpg
```

A szerver leállítása és naplója:

```sh
kill "$(cat "$HOME/vision-http-server.pid")"
tail -f "$HOME/vision-http-server.log"
```

A beépített HTTP szerver nem biztosít hitelesítést. Csak megbízható helyi hálózaton használd, és ne szolgálj ki olyan könyvtárat, amely titkos kulcsokat vagy más érzékeny adatot tartalmaz.
