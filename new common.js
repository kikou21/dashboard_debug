//Fonction pour récupérer le user courant pour le stocker dans session
function currentUser(){
  return sessionStorage.getItem("user");
}

// Fonction pour recommencer les exercices
function resetAndRetry() {
  if (confirm("Voulez-vous vraiment réinitialiser les exercices et libérer les ressources pour recommencer ?")) {
    resetDemoApp(() => {
      currentStep = 0;
      sessionStorage.removeItem("exercises-progress");
      showStep(currentStep);
        if (result){
          document.getElementById("result").innerText = "";
        }
    });
  }
}

//fonction qui réinitialise demo-app 
function resetDemoApp(callback) {
  fetch("/reset-demo-app", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user: currentUser() }) 
  })
  .then(res => res.json())
  .then(() => {
  console.log("🔁 Réinitialisation terminée");
  if (callback)
    callback();
  });
}
    
//fonction pour quitter le dashboard
function logout() {
  if (confirm("Voulez-vous vraiment vous déconnecter et réinitialiser les exercices ?")) {
    //récupère session user pour le transmettre au backend /disconnect
    const user= currentUser();
    if (user) {
      fetch("/disconnect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user, type: "logout" })
      })
      .then(() => {
        // Nettoyage session navigateur et et redirection après le backend
        resetDemoApp(() => {
          sessionStorage.clear();
          window.location.href = "/logout"; 
        });
      })
      .catch(() => {
        // Même si erreur, on force la sortie propre sur page welcome
        sessionStorage.clear();
        window.location.href = "/logout";
      });
    } else {
      //  Cas où aucun user stocké → fallback
      sessionStorage.clear();
      window.location.href = "/logout";
    }
  }
}
    
//Fonction pour retourner à la page fin des exercices
function returnToEnd(){
  sessionStorage.setItem("returnToEnd", "1");
  //récupère le user stocké
  const username = currentUser();
  
  if(username) {
    window.location.href =`/u/${username}/dashboard`;
  } else {
    window.location.href = "/";
  } 
}  

//Fonction pour refaire le quiz
function returnToQuiz(){
  sessionStorage.setItem("returnToQuiz", "1");
  //récupère le user stocké
  const username = currentUser();
  
  if(username) {
    window.location.href =`/u/${username}/quiz`;
  } else {
    window.location.href = "/";
  } 
}  

// Fonction pour gérer la déconnexion (sauvage et pour aller sur demo_app)
function registerDisconnectHandler() {
  window.addEventListener("beforeunload", () => {
    const user = currentUser();
    const leavingForDemo = sessionStorage.getItem("leaving_for_demo");

    if (!user) {
      // Aucun user: ne rien faire
      return;
    } else if (leavingForDemo === "1") {
      // Cdépart vers demo-app → pas de disconnect (pris également en charge par document.addEventLitender)
      console.log(" Retour vers demo-app — pas de disconnect");
      // léger délai pour laisser le flag et la redirection s’exécuter
      setTimeout(() => {
        sessionStorage.removeItem("leaving_for_demo");
      }, 100);
      return;
    } else {
      // Cas : fermeture oenvoi disconnect
      const payload = JSON.stringify({ user });
      console.log(`Déconnexion sauvage détectée pour ${user}`);

      setTimeout(() => {
        try {
          navigator.sendBeacon("/disconnect", payload);
        } catch (e) {
          fetch("/disconnect", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: payload,
            keepalive: true,
          }).catch(() => {});
        }
      }, 100); // 100 ms de délai pour laisser le navigateur traiter l’événement
    }
  });
}


  //********************************keepAlive inactivité ************************************************* */
//inactivité et déconnexion automatique : Deux identifiants pour stocker les IDs des setTimeout. On peut ainsi annuler un timer en cours avec clearTimeout() quand l’utilisateur bouge à nouveau.
let inactivityTimer, warningTimer;

//Durée max d'inactivité et warning
const WARNING_DELAY = 9 * 60 * 1000;   // 9 min préviens  minute avant deconnexion
const LOGOUT_DELAY = 10 * 60 * 1000;   // 10 min

//Création du bandeau qui affichera le message à partir de 9 minutes d'inactivité
const banner = document.createElement("div");
banner.id = "session-warning";
banner.textContent = "⚠️ Votre session expirera dans 1 minute si aucune action n’est effectuée.";
banner.style.display = 'none' //caché au départ
document.body.appendChild(banner);


function resetInactivityTimer() {
  clearTimeout(warningTimer);
  clearTimeout(inactivityTimer);
  //Pour cacher le bandeau lorsque l'utilisateur reprend une action
  banner.style.display = "none";

  //alerte à 9 minutes
  warningTimer = setTimeout(() => {
    banner.style.display = "block";
  }, WARNING_DELAY);
//Déconnexion automatique à 10 minutes
  inactivityTimer = setTimeout(() => {
    banner.style.display = "none";
    resetDemoApp(() => {
      sessionStorage.clear();
      window.location.href = "/";
    });
  }, LOGOUT_DELAY);
}
//écoute des actions utilisateurs
["click", "mousemove", "keypress", "scroll"].forEach(evt =>
  window.addEventListener(evt, resetInactivityTimer)
);

// ------------------- KeepAlive  déconnexion sauvage -------------------
const KEEPALIVE_INTERVAL = 30000; // 30 secondes

function sendKeepAlive() {
  const user = currentUser();
  if (!user) return;

  fetch("/keepAlive", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user }),
    keepalive: true
  }).catch(() => {});
}

  //*******************fin du keepAlive  */
// --------Gère la fermeture ou le rechargement du dashboard lorsqu'il va sur demo-app pour prévenir suppression connected redis-------------------
document.addEventListener("DOMContentLoaded", () => {
  // Ici bloc openUrl/addEventListener sur les liens qui vont vers demo-ap
  document.querySelectorAll("a").forEach(link => {
    if (link.textContent.includes("Accéder à l'application pour effectuer l'exercice")) {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        console.log("clic détecté sur le lien demo-app");
        sessionStorage.setItem("leaving_for_demo", "1");
        sessionStorage.setItem("dashScroll", String(window.scrollY));

        setTimeout(() => {
          console.log("➡️ redirection vers demo-app");
          window.location.href = link.href;
        }, 100);
      });
    }
  });
});



// Envoie un ping toutes les 30s tant que la page est ouverte
setInterval(sendKeepAlive, KEEPALIVE_INTERVAL);

//premier ping immédiat dès que user connecté
/* const user = currentUser();
if (sessionStorage.user) {
sendKeepAlive();
}else{
  //si session pas encore prête retente après 1 s
  setTimeout(() => { 
    if (sessionStorage.user) 
      sendKeepAlive(); 
   }, 1000);
} */


// Tentative de notification quand l'utilisateur ferme brutalement la fenêtre
/* window.addEventListener("visibilitychange", () => {
  const user = currentUser();
  if (document.visibilityState === "hidden" && user) {
    //Si l'utilisateur ferme la page sendBeacon préviens le backend (Redis)
    console.log("debug je suis passé par visibility ")
    navigator.sendBeacon("/disconnect", JSON.stringify({ user }));
  }
});*/


//initialisation pour lancer le timer dès que la page s'ouvre
resetInactivityTimer();
//Active la gestion de la deconnexion sauvage dès le chargement
registerDisconnectHandler();
