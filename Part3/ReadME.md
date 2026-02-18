# Section 3 — Intégration dans une architecture Edge complète  
(MQTT + EdgeX + supervision distribuée)

---

# 1. Pourquoi cette section existe

Dans les Sections 1 et 2, vous avez construit :

- une boucle périodique 20 ms,
- une mesure de jitter et de deadlines,
- une adaptation locale (mode NORMAL / DEGRADED).

Votre système fonctionne.

Mais il est **isolé**.

Dans un système embarqué réel :

- les devices envoient des métriques,
- ils sont supervisés,
- ils peuvent être reconfigurés à distance,
- ils s’intègrent dans une plateforme plus large.

Objectif de cette section :

> Construire une architecture Edge réaliste  
> où la boucle 20 ms reste locale  
> et où la supervision/orchestration est déportée.

---

# 2. Pourquoi MQTT ?

## 2.1 Problème architectural

Si chaque device devait communiquer directement avec tous les autres :

- multiplication des connexions,
- couplage fort,
- architecture fragile.

On introduit donc un **broker** central.

---

## 2.2 Modèle Publish / Subscribe

MQTT fonctionne ainsi :

- Un device publie un message sur un *topic*.
- Il ne sait pas qui écoute.
- Le broker distribue aux abonnés.

Exemple :
```yaml
tp/device1/metrics
tp/device1/cmd
```

Cela permet :

- découplage,
- extensibilité,
- architecture scalable,
- simplicité côté embarqué.

MQTT est léger et adapté aux systèmes embarqués.

---

# 3. Pourquoi EdgeX ?

MQTT transporte des messages.
Mais il ne :

- structure pas les données,
- ne stocke pas proprement,
- n’expose pas d’API REST,
- ne gère pas un registre de devices.

EdgeX apporte :

- un registre de devices (Core Metadata),
- un stockage structuré (Core Data),
- une API de commande (Core Command),
- un modèle standardisé (events / readings).

Résumé :

MQTT = transport  
EdgeX = plateforme de structuration et d’orchestration

---

# 4. Architecture réseau à mettre en place

On a deux solutions (voire trois) ici pour mettre en place un réseau : 
- juste une connexion ethernet entre deux devices, l'un jouant le rôle de la gateway. On est donc limités à deux devices.
- tous les connecter au WiFi de l'école mais cela ne fonctionnera que si ils sont sur le même sous réseau...
- Mettre un des devices en mode "access point", les autres s'y connectent et on se retrouve avec un sous réseau privé.

En cas de difficultés pour mettre cela en place, j'ai des TPs dans mon github de disponibles avec des mises en oeuvre simples (TP1/TP2 ISANUM).

---

# 5. Mise en place MQTT

On va commencer par une mise en place simple pour être sûr que cela fonctionne bien.

## 5.1 Sur la gateway et lee device

```bash
sudo apt install -y mosquitto mosquitto-clients
sudo systemctl enable --now mosquitto
```

Test rapide :

Gateway :

```bash
mosquitto_sub -h localhost -t test/topic
```

Device :

```bash
mosquitto_pub -h IP_GATEWAY -t test/topic -m "hello"
```

Si on voit le message apparaitre tout fonctionne, sinon ce n'est pas le cas...

---

# 6. Intégrer MQTT dans votre boucle Python

À ce stade, vous avez :

- une boucle périodique de 20 ms,
- des métriques (jitter, miss_rate, workload),
- un mode NORMAL / DEGRADED,
- une adaptation locale.

Nous allons maintenant connecter ce système au reste du monde.

Mais attention :

Votre boucle 20 ms est un **chemin critique**.

Elle ne doit **jamais dépendre du réseau**.

Si le Wi-Fi devient instable, si le broker est lent,
la boucle doit continuer à fonctionner correctement.

C’est un principe fondamental des architectures embarquées robustes :

> Le contrôle critique est local.  
> La supervision est distante.

---

## 6.1 Ce que nous allons ajouter

Nous allons ajouter deux mécanismes :

1. Une publication périodique des métriques (toutes les 200 ms).
2. Une réception asynchrone de commandes (SetMode).

Ces deux éléments doivent être :

- non bloquants,
- découplés du cycle 20 ms,
- simples.

---

## 6.2 Installer la bibliothèque MQTT

Sur chaque device :

```bash
pip install paho-mqtt
```

Pourquoi une bibliothèque dédiée ?

Parce que MQTT n’est pas un simple socket.send().

Il faut :

- gérer la connexion,
- gérer la reconnexion,
- gérer les abonnements,
- gérer les callbacks,
- gérer les paquets TCP.

La bibliothèque paho-mqtt encapsule tout cela.

---

## 6.3 Comprendre le modèle d’exécution

Un point crucial :

Votre boucle 20 ms tourne en permanence.

Si vous faites :

```python
mqtt_client.loop_forever()
```

Votre programme ne fera plus que ça.

C’est pour cela que nous utilisons :

```python
mqtt_client.loop_start()
```

Cela démarre un thread interne qui gère :

- les échanges réseau,
- la réception des messages,
- les callbacks.

Votre boucle principale reste indépendante.

---

## 6.4 Ajouter la configuration

En haut de votre fichier :

```python
import json
import paho.mqtt.client as mqtt
import time

IP_GATEWAY = "192.168.X.X"
MQTT_PORT = 1883

TOPIC_METRICS = "tp/device1/metrics"
TOPIC_CMD = "tp/device1/cmd"

PUBLISH_INTERVAL = 0.2  # 200 ms
```

Pourquoi 200 ms ?

> Votre boucle est à 20 ms (50 Hz). Publier à 50 Hz serait inutile et coûteux.

La supervision n’a pas besoin d’une fréquence aussi élevée.

On sépare donc :

- 20 ms → contrôle
- 200 ms → supervision

---

## 6.5 Initialisation MQTT (avant la boucle)

Ajoutez :

```python
mode = "NORMAL"

def on_message(client, userdata, msg):
    global mode
    try:
        payload = json.loads(msg.payload.decode())
        if "Mode" in payload:
            mode = payload["Mode"]
            print("Mode updated:", mode)
    except Exception as e:
        print("Invalid command received:", e)

mqtt_client = mqtt.Client()
mqtt_client.on_message = on_message

mqtt_client.connect(IP_GATEWAY, MQTT_PORT, 60)

mqtt_client.subscribe(TOPIC_CMD)

mqtt_client.loop_start()
```

À comprendre :
- `on_message` est appelée automatiquement lorsqu’un message arrive.

Elle ne doit faire qu’une chose simple : modifier une variable.

Elle ne doit pas faire de calcul lourd.

Pourquoi ?

Parce que même si elle tourne dans un autre thread, vous ne voulez pas introduire d’instabilité.

---

## 6.6 Ajouter la publication lente

Dans votre boucle principale :

```python
last_pub = time.perf_counter()

while True:

    # --- Boucle 20 ms ici ---
    # calcul jitter, miss_rate, workload

    now = time.perf_counter()

    if now - last_pub >= PUBLISH_INTERVAL:

        payload = {
            "timestamp": time.time(),
            "mode": mode,
            "jitter_mean": jitter_mean,
            "jitter_max": jitter_max,
            "miss_rate": miss_rate,
            "workload": workload
        }

        mqtt_client.publish(TOPIC_METRICS, json.dumps(payload))
        last_pub = now
```

Point important :

> La publication est conditionnelle. Elle ne perturbe pas la périodicité 20 ms.

---

## 6.7 Vérification essentielle

Après intégration MQTT :
1. Mesurez à nouveau la période moyenne.
2. Comparez le jitter maximum.
3. Vérifiez que le miss_rate ne dégrade pas.

Si votre système devient instable : vous avez introduit un blocage, ou la publication est trop fréquente.

C’est un test critique.

---

# 7. Intégration avec EdgeX (

Maintenant que MQTT fonctionne, nous allons connecter cette remontée à une plateforme Edge réelle.

---

## 7.1 Comprendre ce que EdgeX va faire

EdgeX ne remplace pas MQTT. Il s’insère derrière.

Il va :

- écouter les topics MQTT,
- transformer les messages JSON en événements structurés,
- les stocker,
- exposer une API REST.

C’est une couche de structuration.

---

## 7.2 Déployer EdgeX

Sur la gateway :

```bash
docker compose up -d
```

Vérifier :

```bash
docker ps
```

Vérifier les endpoints :

```bash
curl http://IP_GATEWAY:59881/api/v2/ping
curl http://IP_GATEWAY:59880/api/v2/ping
curl http://IP_GATEWAY:59882/api/v2/ping
```

Chaque service doit répondre.

---

## 7.3 Comprendre le rôle des services

Core Metadata : registre des devices

Core Data : stockage des événements

Core Command : point d’entrée des commandes

device-mqtt : passerelle entre MQTT et EdgeX

---

## 7.4 Vérifier l’ingestion des métriques

Sur la gateway :

```bash
mosquitto_sub -h localhost -t "tp/device1/metrics"
```

Puis :

```bash
curl "http://IP_GATEWAY:59880/api/v2/event?limit=5"
```

Vous devez voir :

- deviceName
- origin
- readings

Chaque message MQTT devient un Event EdgeX.

---

# 8. EdgeX : première vérification via l’UI (sans encore parler de commandes)

À ce stade, votre objectif est simplement de vérifier que la **plateforme EdgeX est démarrée**.

## 8.1 Accéder à l’UI

Ouvrir :

- `http://IP_GATEWAY:4000`

Si cela ne répond pas :

```bash
docker ps | grep -E "ui|edgex"
```

et vérifiez que le port 4000 est bien exposé dans le docker-compose.yml.

# 8.2 Ce que vous devez constater dans l’UI

Dans l’UI, repérez :
- les services EdgeX principaux (Core Data, Core Metadata, Core Command, device-mqtt)
- leur état général (UP)

Important :
À ce moment, il est normal de ne voir aucun device ou très peu d’éléments.
EdgeX ne “découvre” pas vos devices automatiquement : il faut les déclarer.

> L’UI sert ici à vérifier : “la plateforme tourne”, pas encore “le système complet fonctionne”.

---

# 9. Définir ce qu’un device sait faire : injection du Device Profile

EdgeX sépare deux choses :

- **Device Profile** : description des capacités (ressources et commandes possibles)
- **Device** : une instance concrète (nom, protocole, paramètres MQTT)

Dans cette étape, vous allez d’abord injecter le profile.
C’est ce profile qui décrit, par exemple, qu’une commande SetMode existe.

## 9.1 Injecter le profile

Sur la gateway :

```bash
curl -X POST "http://IP_GATEWAY:59881/api/v2/deviceprofile" \
  -H "Content-Type: application/yaml" \
  --data-binary "@profile-device-mode.yaml"
```

Vérifier :

```bash
curl "http://IP_GATEWAY:59881/api/v2/deviceprofile/name/device-mode-profile" | head
```

# 9.2 Vérifier dans l’UI

Dans l’UI :

- aller dans Device Profiles
- vérifier que device-mode-profile apparaît
- ouvrir le profile et repérer :
    - la ressource Mode
    - la commande SetMode

Expliquez la différence entre “ressource” (Mode) et “commande” (SetMode). pourquoi EdgeX a besoin de ce fichier pour standardiser une commande ?

---

# 10. Associer ce profile à un device réel : injection du Device

Le profile décrit des capacités “en général”.
Maintenant, on déclare un device concret (device1) en précisant comment lui parler (ici MQTT).

## 10.1 Injecter le device

```bash
curl -X POST "http://IP_GATEWAY:59881/api/v2/device" \
  -H "Content-Type: application/json" \
  --data-binary "@device1.json"
```

Vérifier :

```bash
curl "http://IP_GATEWAY:59881/api/v2/device/name/device1" | head
```

## 10.2 Vérifier dans l’UI

Dans l’UI :

- aller dans Devices
- vérifier que device1 apparaît
- vérifier qu’il est associé au profile device-mode-profile

> À ce stade : EdgeX sait que device1 existe, et sait qu’il peut recevoir une commande SetMode.

---

# 11. Observer les données (Events) puis tester la commande (SetMode)

On valide maintenant deux choses différentes :

A) la remontée de métriques (MQTT → EdgeX → Core Data)
B) la boucle de retour (EdgeX → MQTT → device)

11.A Remontée : vérifier les Events
11.A.1 Vérification côté MQTT (CLI)

Sur la gateway :

mosquitto_sub -h localhost -t "tp/device1/metrics" -v


Si vous ne voyez rien, le problème est côté device / réseau MQTT.

### 11.A.2 Vérification côté EdgeX (CLI)

```bash
curl "http://IP_GATEWAY:59880/api/v2/event?limit=5" | head -n 60
```

### 11.A.3 Vérification côté UI

Dans l’UI → Events :
- ouvrir un event récent
- repérer les readings (jitter, workload, etc.)
- vérifier que l’arrivée est ~toutes les 200 ms (sans être parfaitement régulière)

Question :
- pourquoi l’intervalle n’est-il pas strictement 200 ms ? (au moins 3 causes : Wi-Fi, scheduling, docker, broker, etc.)

## 11.B Boucle de retour : exécuter SetMode

### 11.B.1 Test via l’UI (plus intuitif)

UI → **Devices** → `device1` → **Commands** → SetMode

- envoyer DEGRADED, puis NORMAL

### 11.B.2 Vérifier que la commande sort bien en MQTT (debug)

Sur la gateway :

```bash
mosquitto_sub -h localhost -t "tp/device1/cmd" -v
```

# 11.B.3 Vérifier côté device

Côté device, vous devez voir :
- réception du message `{"Mode":"..."}` (log/print)
- mise à jour de la variable `mode`
- modification progressive du comportement (workload ↓ en DEGRADED)

### 11.B.4 Vérifier dans les Events suivants

Dans l’UI → Events :

- l’event suivant doit contenir `mode: DEGRADED` (si vous publiez ce champ)
- et idéalement montrer une évolution des métriques

--- 

# 12. Point pédagogique clé

- Le profile définit ce qu’un device sait faire (ex : SetMode).
- Le device instancie un profile et précise “comment lui parler” (MQTT + topics).
- Les Events montrent la supervision (retardée, échantillonnée).
- La commande SetMode est une boucle de retour soft real-time.
