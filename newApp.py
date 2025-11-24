import os
import time
import json
import redis
import threading
import time
import sys
import requests

from flask import Flask, render_template, send_file, jsonify, request, redirect
#pour requêtes cross origin demo-app dashboard pour keepAlive
from flask_cors import CORS

from kubernetes import client, config

# Charge la configuration Kubernetes une seule fois
try:
    config.load_incluster_config()
    print("Config in-cluster chargée")
except:
    config.load_kube_config()
    print("Config locale chargée")

# Clients Kubernetes
core_v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()

RELEASE_NAME = os.getenv("RELEASE_NAME", "training-dashboard-dashboard")
REDIS_HOST = os.getenv("REDIS_HOST", "training-dashboard-redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


app = Flask(__name__,
            template_folder="frontend/templates",
            static_folder="frontend/static")

#autorise uniquement les origines url dashboard et demo-app
CORS(app, resources={
    r"/*": {
        "origins": [
            "http://dashboard.xxxxxxxxxxx.fr",
            "http://demo.xxxxxxxxxxxxxxx.fr"
        ]
    }
})

app.logger.setLevel ("DEBUG")

#Construit le namespace de l'utilisateur à partir de son login
def get_namespace(username: str) -> str:
    username= username.lower()
    return f"acculturation-{username}"

#récupère et retourne le nom du déploiement demo-app ainsi que le ns utilisateur en fonction des variables d'environnement injectées 
def get_demo_app_deployment(username: str):
    username = username.lower()
    deployment_name = f"{RELEASE_NAME}-demo-app-{username}"
    ns = get_namespace(username)
    return apps_v1.read_namespaced_deployment(name=deployment_name, namespace=ns)

def wait_for_replicas(deployment_name: str, namespace: str, expected_replicas: int, timeout: int = 120):
    """Attend que le nombre de pods *Running* atteigne expected_replicas."""
    config.load_incluster_config()
    core_v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()

    label_selector = ""
    try:
        deployment = apps_v1.read_namespaced_deployment(deployment_name, namespace)
        label_selector = ",".join([f"{k}={v}" for k, v in deployment.spec.selector.match_labels.items()])
    except Exception as e:
        print(f"[ERROR] Impossible de récupérer les labels du déploiement : {e}")
        return False

    start = time.time()
    while time.time() - start < timeout:
        try:
            pods = core_v1.list_namespaced_pod(namespace=namespace, label_selector=label_selector)
            running = [p for p in pods.items if p.status.phase == "Running"]
            if len(running) == expected_replicas:
                return True
        except Exception as e:
            print("Erreur pendant la vérification des pods:", e)

        time.sleep(2)

    return False

#*************************************************************routes******************************************************************
# Favicon (évite une erreur 404)
@app.route("/favicon.ico")
def favicon():
    return '', 204


# Page de login
@app.route("/")
def redirect_to_login():
    return render_template("login.html")  

@app.route("/login", methods=["GET","POST"])
def login():
    
    if request.method == "GET":
        return render_template("login.html")

    #------------- SINON POST----------------------------------
    #Récupère le username
    username= (request.form.get("username") or "").strip().lower()
    
    #Récupère la liste des utilisateurs valides depuis ENV deployment et vérifie si user est présent
    valid_users = os.getenv("VALID_USERS", "").split(",")
    valid_users = [u.strip().lower()for u in valid_users if u.strip()]
         
    # Cas 1 si identitiant non saisi
    if not username:
        return render_template("login.html", error="identifiant non saisi merci d'entrer un identifiant")
        
    # Cas 2 si identifiant pas dans la liste user valide (values.yaml)
    if username not in valid_users:
        return render_template("login.html", error="utilisateur non autorisé, merci d'entrer un identifiant valide")
        
    # Cas 3 Créé l'utilisateur  si l'utilisateur n'est pas  déjà connecté ailleurs (clé Redis existante)
    key = f"user:{username}:connected"
    created = bool(r.set(name=key, value="1", nx=True, ex=3600))  # True si la clé est crée False sinon
    #logs
    app.logger.info(f"[LOGIN DEBUG] set({key}, nx=True, ex=3600) -> {created}") 
    ttl = r.ttl(key)
    app.logger.info(f"[LOGIN DEBUG] TTL actuel de {key}= {ttl}")

    #Si clé non créé (false)
    if not created:
        app.logger.warning(f"[LOGIN BLOCKED] Tentative double connexion pour {username}")
        return render_template("login.html", user_taken=f"L'utilisateur « {username} » est déjà connecté sur une autre session."
        )

    #  Sinon,  nouvelle connexion autorisée  nettoie anciennes traces des éventuelles connexions précédentes
    r.delete(f"user:{username}:closed_at")
    r.delete(f"user:{username}:last_seen")
    app.logger.info(f"[LOGIN OK] {username} connecté.") 
    
    # Redirection vers la page welcome pour l'utilisateur connecté
    return redirect(f"/u/{username}/welcome")
         
  
#Pour utiliser la liste des users valides pour utiliser dans fetch
@app.route("/valid-users")
def valid_users():
    valid_users = os.getenv("VALID_USERS") or ""
    valid_users = [u.strip().lower() for u in valid_users.split(",") if u.strip()]
    return jsonify({"validUsers":valid_users}) 
 

# Page d’accueil
@app.route("/u/<username>/welcome")
def user_dashboard(username):
    username= username.lower()
    #vérifie que l'utilisateur est bien défini dans values
    valid_users = os.getenv("VALID_USERS", "").split(",")
    
    if username not in [u.strip().lower() for u in valid_users if u.strip()]:
        return "utilisateur non autorisé",403
    
    ns = get_namespace(username)
    app.logger.info(f"Dashboard ouvert pour {username} (namespace {ns})")
    return render_template("welcome.html", username=username)


# affichage du dashboard des exercices
@app.route("/u/<username>/dashboard")
def dashboard(username):
    username= username.lower()
    return render_template("index.html", username=username)

#Affiche page de confirmation quitter
@app.route("/goodBye")
def goodBye():
       return render_template("goodBye.html")

#affiche l'architecture du site
@app.route("/u/<username>/seeMore")
def see_more(username):
    username= username.lower()
    return render_template("seeMore.html", username=username)

#affichage le quiz html
@app.route("/u/<username>/quiz")
def quiz_page(username):
    username= username.lower()
    return render_template("quiz.html", username=username)

#charge fichier quiz
@app.route("/quiz/<name>.json")
def get_quiz_file(name):
    local_path = f"frontend/exercises/{name}.json"
    if os.path.exists(local_path):
        return send_file(local_path, mimetype="application/json")
    local_path = f"frontend/quizzes/{name}.json"
    if os.path.exists(local_path):
        return send_file(local_path, mimetype="application/json")
    return jsonify({"error": "Fichier quiz non trouvé"}), 404

#ajoute route pour corriger le quiz
@app.route("/u/<username>/submit-quiz", methods=["POST"])
def submit_quiz(username):
    username= username.lower()
    quiz_path = "frontend/quizzes/quiz.json"
    with open(quiz_path, "r", encoding="utf-8") as f:
        quiz = json.load(f)

    results = []
    score = 0

    for i, q in enumerate(quiz):
        user_answer = request.form.get(f"q{i}")
        correct = user_answer == q["answer"]
        if correct:
            score += 1
        results.append({
            "question": q["question"],
            "user_answer": user_answer,
            "correct_answer": q["answer"],
            "correct": correct,
            "explanation": q["explanation"]
        })

    ns = get_namespace(username)
    app.logger.info(f"{username} (ns {ns}) a terminé le quiz avec {score}/{len(quiz)}")
    return render_template("quizResult.html", username=username, total=len(quiz), results=results, score=score )

# Charge un fichier d’exercice (demo.json)
@app.route("/exercises/<name>.json")
def get_exercise_file(name):
    local_path = f"frontend/exercices/{name}.json"
    if os.path.exists(local_path):
        return send_file(local_path, mimetype="application/json")
    local_path = f"frontend/exercises/{name}.json"
    if os.path.exists(local_path):
        return send_file(local_path, mimetype="application/json")
    return jsonify({"error": "Fichier exercice non trouvé"}), 404



# Charge un fichier de manifestes (manifests-demo.json)
# @app.route("/manifests/<name>.json")
# def get_manifest(name):
#     path = f"frontend/manifests/manifests-{name}.json"
#     if os.path.exists(path):
#         try:
#             with open(path) as f:
#                 return jsonify(json.load(f))
#         except Exception as e:
#             return jsonify({"error": f"Erreur JSON: {e}"}), 500
#     return jsonify({"error": f"Fichier manifests-{name}.json non trouvé"}), 404



# Exécute une action (create, scale, list, openUrl scalePrompt)
@app.route("/run-action/<step_id>", methods=["POST"])
def run_action(step_id):
    try:
        action = request.get_json()
        action_type = action.get("type")

        if action_type == "create":
            return handle_create(action)
        elif action_type == "scale":
            return handle_scale(action)
        elif action_type == "list":
            return handle_list(action)
        elif action["type"] == "scalePrompt":
            return handle_scale(action) 
        # pour openUrl, rien à faire côté backend (c’est purement front)
        elif action_type == "openUrl":
            return jsonify({"status": "Ouverture du lien gérée côté client"}), 200
        else:
            return jsonify({"error": f"Action non supportée : {action['type']}"}), 400
        
    except Exception as e:
        print(" Erreur dans run_action:", e)
        return jsonify({"error": f"Erreur interne : {str(e)}"}), 500

# récupère releaseName et namespace utilisater de demo-app

#Reset l'application demo après fin des exercices   
@app.route("/reset-demo-app", methods=["POST"])
def reset_demo_app():
    try:
        api = client.AppsV1Api()
        username = request.json.get("user").lower()
        name = f"{RELEASE_NAME}-demo-app-{username}"
        if not username:
            return jsonify({"error": "Utilisateur manquant"}), 400
        ns = get_namespace(username)
        body = {
            "spec": {"replicas": 1}
        }
        api.patch_namespaced_deployment_scale(name, ns, body)
        return jsonify({"status": "Déploiement remis à 1 pod"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
 #A la déconnexion redirige sur page goodBye   
@app.route("/logout")
def logout():
    return redirect("/goodBye")

# Route appelée périodiquement par le navigateur (via JS sendKeepAlive) pour indiquer que l'utilisateur est toujours actif sur le dashboard.
@app.route("/keepAlive", methods=["POST"])
def keep_alive():
    try:
        # Récupère les données JSON envoyées par le navigateur (POST body) silent=True = ne lève pas d’erreur si le JSON est vide
        data = request.get_json(silent=True) or {}
        
        # Extraction du nom d’utilisateur depuis le Json
        username = (data.get("user") or "").strip().lower()
     
        # Si aucun utilisateur n'est transmis, on ignore simplement (pas d'erreur) 
        # sendBacon (JS) ne garantit pas toujours le payload, il peut envoyer la requête avant que le jsonsoit complétement construit..
        # #si on force erreur messages d'erreurs risque de faux messages d'erreur
        if not username:
            app.logger.warning("keepAlive sans user")
            return "", 204  #no content
        
        #Refuser keepAlive si "connected" n'existe plus
        key_connected = f"user:{username}:connected"
     
        if not r.exists(key_connected):
             app.logger.info(f"[keepAlive] {username} plus connecté, pas de keepAlive possible")
             return "", 401
               
        #Enregistre dans Redis l’heure actuelle comme "dernière activité"
        ts = int(time.time())
        r.set(f"user:{username}:last_seen", ts, ex=600 )
        r.expire(key_connected, 3600) # refresh TTL du connected
        # Réponse HTTP vide, mais avec code 204 (OK sans contenu)
        app.logger.info(f"[keepAlive] {username} last_seen={ts}")
        return "", 204
    
    # En cas d’erreur (ex: problème Redis), on logue dans le fichier Flask   
    except Exception as e:
        app.logger.error(f"keepAlive error: {e}")
        return "", 500

#gestion de la deconnexion   Route unique pour : les fermetures sauvages (sendBeacon), les déconnexions manuelles (logout via JS) Supprime immédiatement les clés Redis de l'utilisateur.
@app.route("/disconnect", methods=["POST"])
def disconnect():
   
    #force encodage UTF-8 sur sortie standard du processus Python
    try:
      sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    
    #initialisés d'avance pour éviter que cela ne s'initialise pas proprement si json.loads plantait
    username = ""
    data = {}
    
    try:
         # Récupère le JSON même si le header Content-Type est absent
        try:
            if request.data:
              data = json.loads(request.data.decode("utf-8"))
        except Exception as e:
             app.logger.warning(f"[disconnect] JSON invalide: {e}")
            
         # Extraction du nom d’utilisateur
        username = (data.get("user") or "").strip().lower()
        
        # Extraction du type (pour gérer déconnexion bouton )
        req_type= (data.get("type") or "").lower()
        
         # Si un utilisateur est bien fourni on enregistre dans Redis l’heure actuelle sous closed_at
        if username:
            app.logger.info(f"[logout] {username} je suis dans username ")
            #timestamp actuel
            ts = int(time.time())
            
            #Si déconnexion via clic boutton deconnexion purge immédiate
            if req_type in ["logout", "force"]:
            # Supprime la clé de connexion et les autres traces
             r.delete(f"user:{username}:connected")
             r.delete(f"user:{username}:last_seen")
             r.delete(f"user:{username}:closed_at")
             app.logger.info(f"[logout] {username} déconnecté manuellement ")
            else:
            #si fermeture sauvage, enregistre le moment de fermeture 
             r.set(f"user:{username}:closed_at", ts)    
             r.delete(f"user:{username}:connected")    
             r.delete(f"user:{username}:last_seen")
            app.logger.info(f"[disconnect] Clés Redis supprimées pour {username} (fermeture sauvage t)closed_at={ts}")
            #reset automatique de la demo-app si onglet fermé brutalement via dns dashboard car route plus accessible en locale à la fermeture.
            try:
                requests.post("http://training-dashboard-dashboard:5000/reset-demo-app", json={"user": username})
                app.logger.info(f"[disconnect] reset demo-app faite pour {username}")
            except Exception as e:
              app.logger.warning(f"[disconnect] reset demo-app en echec pour {username} : {e}")
        else:
            app.logger.warning("[disconnect] appelé sans user — erreur ignorée")
            
        return "", 204
    # Logue l’erreur si problème d’accès à Redis ou autre
    except Exception as e:
        app.logger.error(f"disconnect error: {e}")
        return "", 500



#*****************************************************actions***************************************************

# Création d’une ressource (avec ou sans payloadSource) pas utilisé mais laissé pour le cas où nouveaux exercices create
def handle_create(action):
    resource = action["resource"]
    payload = action.get("payload")
    ns = get_namespace(action["user"])
    
    # Si payloadSource présent → chercher dans manifests
    if not payload and "payloadSource" in action:
        path = "frontend/manifests/manifests-demo.json"
        if not os.path.exists(path):
            return jsonify({"error": "Fichier de manifestes manquant"}), 500
        with open(path) as f:
            manifest = json.load(f)
            payload = manifest.get(action["payloadSource"])
            if not payload:
                return jsonify({"error": f"Payload {action['payloadSource']} introuvable"}), 400

    if resource == "deployment":
        apps_v1.create_namespaced_deployment(namespace=ns, body=payload)
        return jsonify({"status": f"✅ Déploiement {payload['metadata']['name']} créé."})
    elif resource == "service":
        core_v1.create_namespaced_service(namespace=ns, body=payload)
        return jsonify({"status": f"✅ Service {payload['metadata']['name']} créé."})
    else:
        return jsonify({"error": f"Ressource {resource} non prise en charge."}), 400 
    
# Mise à l’échelle (scale)
def handle_scale(action):
    print(" Action reçue dans handle_scale:", action)
    username = action["user"].lower()
    name = f"{RELEASE_NAME}-demo-app-{username}"
    ns = get_namespace(username)
    
  
    replicas = action["replicas"]
    timeout = action.get("timeout", 120)
    # user = action.get("user", "anonyme")
    # print(f"[INFO] Action de l'utilisateur : {user}")

    config.load_incluster_config()
    api = client.AppsV1Api()

    try:
        # Vérifie l'état actuel
        deployment = api.read_namespaced_deployment(name, ns)
        current = deployment.spec.replicas

        if current == replicas:
            return jsonify({"status": f"ℹ️ L'application {name} est déjà à {replicas} réplicas."})

        # Sinon on applique le scale
        body = {"spec": {"replicas": replicas}}
        api.patch_namespaced_deployment_scale(name, ns, body)

        # Et on attend que les pods soient prêts
        if wait_for_replicas(name, ns, expected_replicas=replicas, timeout=timeout):
            return jsonify({"status": f"✅ {name} mis à l’échelle à {replicas} pod(s), l'application demo-app tourne maintenant sur {replicas} pod(s)."})
        else:
            return jsonify({"error": f"⏳ Les pods ne sont pas prêts après {timeout}s."}), 408

    except Exception as e:
        app.logger.error (
        f"[handle_scale] erreur pour user = {action.get('user')}"
        f"namespace={get_namespace(action.get('user'))}: {e}"
            )
        return jsonify({"error": str(e)}), 500
# Liste les pods

def handle_list(action):
    
    username = action["user"].lower()
    name = f"{RELEASE_NAME}-demo-app-{username}"
    selector = f"app={name}"
    ns = get_namespace(username)
   
    expected_count = action.get("expectedPods")  
    timeout = action.get("timeout", 120)

    pods = core_v1.list_namespaced_pod(namespace=ns, label_selector=selector)

    #  Exclure les pods non "Running"
    running_pods = [
        p.metadata.name for p in pods.items
        if p.status.phase == "Running"
    ]

    print(f"[INFO] ➔ Pods Running sélectionnés : {running_pods}")

    if expected_count is not None:
        # Attente si les pods ne sont pas encore prêts
        if len(running_pods) < expected_count:
            if wait_for_replicas(name, ns, expected_replicas=expected_count, timeout=timeout):
                return handle_list(action)  # relance après attente
            else:
                return jsonify({"error": f"⏳ Seulement {len(running_pods)} pod(s) Running prêts après {timeout}s."}), 408

    # 🔠 Mise en forme multilignes
    pod_lines = "\n".join([f"• {name}" for name in running_pods])
    return jsonify({
        "status": f"{len(running_pods)} pod(s) trouvé(s) :\n{pod_lines}"
    })

#Thread de nettoyage des utilisateurs inactifs ou déconnectés sauvagement
#Fonction qui tourne en arrière plan et vérifie régulièrement l'état des utilisateurs dans Redis pour détecter les inactifs depuis 10mn et fermeture fenetre 3mn
# Thread de nettoyage des utilisateurs inactifs ou déconnectés sauvagement
# Fonction qui tourne en arrière-plan et vérifie régulièrement l'état des utilisateurs dans Redis
# pour détecter les inactifs depuis 10 min et fermeture fenêtre > 3 min
def cleanup_inactive_users():
    INACTIVITY_TIMEOUT = 10 * 60   # 10 minutes d'inactivité max
    SHUTDOWN_GRACE = 1 * 45        # 45 secondes de grâce après fermeture

    print("[cleanup] vérification des sessions actives")

    while True:
        now = int(time.time())

        # On parcourt toutes les clés Redis du type user:xxx:connected
        for key in list (r.scan_iter("user:*:connected")) + list (r.scan_iter("user:*:closed_at")):
            print(f"vérifie {key}")
            parts = key.split(":")
            if len(parts) < 3:
                continue
            username = parts[1]

            last_seen = r.get(f"user:{username}:last_seen")
            closed_at = r.get(f"user:{username}:closed_at")

            # ---- Cas 1 : utilisateur inactif trop longtemps ----
            if last_seen:
                try:
                    last_seen = int(last_seen)
                    if now - last_seen > INACTIVITY_TIMEOUT:
                         # Suppression des clés Redis
                        r.delete(f"user:{username}:connected")
                        r.delete(f"user:{username}:last_seen")
                        r.delete(f"user:{username}:closed_at")
                        # Purge demo-app (remet à 1 pod)
                        try:
                            ns = get_namespace(username)
                            deployment_name = f"{RELEASE_NAME}-demo-app-{username}"
                            body = {"spec": {"replicas": 1}}
                            apps_v1.patch_namespaced_deployment_scale(deployment_name, ns, body)
                            app.logger.info(f"[CLEANUP] Demo-app de {username} remise à 1 pod (inactivité > 10 min)")
                        except Exception as e:
                            app.logger.warning(f"[CLEANUP] Erreur purge demo-app {username}: {e}")
                       
                        print(f" {username} supprimé (inactivité > 10 min)")
                        continue
                except ValueError:
                    pass
                
             # Cas 2 : fermeture sauvage non suivie de reconnexion
            if closed_at:
                try:
                    closed_at = int(closed_at)
                    # Si la fenêtre a été fermée et que 45 secondes se sont écoulées
                    if now - closed_at > SHUTDOWN_GRACE:
                        # On supprime la clé connected → utilisateur “libéré”
                        r.delete(f"user:{username}:connected")
                        r.delete(f"user:{username}:closed_at")
                        r.delete(f"user:{username}:last_seen")
                        print(f"💤 {username} supprimé (fermeture sauvage > 45 secondes)")
                        continue
                except ValueError:
                    pass
        
        # Attendre 1 m avant de refaire une vérification
        time.sleep(60)


# Démarrage unique du thread de nettoayage au lancement du serveur Flask (sécurisé multi-workers)
#Gunicorn créé plusiers processus (workers)Pour éviter que chaque worker démarre son propre thread de nettoyage, on utilise une var d'environnement temporaire comme verrrou

#Si el exixte déjà on ne relance pas le thread
if os.environ.get("CLEANUP_THREAD_STARTED") != "1" :
    #lance le thread en tâche defond. Ce thread est marqué daemon=True, ce qui signifie qu’il s’arrêtera automatiquement quand le processus Flask se termine.
    threading.Thread(target=cleanup_inactive_users, daemon=True).start()
    #Inscrit que le thread est déjà démmarré
    os.environ["CLEANUP_THREAD_STARTED"] = "1"
    #log pour vérifier dans les logs gunicorn ou flask
    print("Thread de nettoyage lancé")

# Lance le serveur Flask si gunicorn pas lancéc
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
