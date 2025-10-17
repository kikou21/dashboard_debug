ajouter 
else {
  const payload = JSON.stringify({ user });

  // 🛑 Stoppe immédiatement le keepAlive pour éviter les requêtes concurrentes
  if (window.keepAliveIntervalId) {
    clearInterval(window.keepAliveIntervalId);
    console.log("⏹️ KeepAlive arrêté avant fermeture.");
  }

  try {
    navigator.sendBeacon(`${dashboard_url}/disconnect`, payload);
  } catch (e) {
    fetch(`${dashboard_url}/disconnect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload,
      keepalive: true
    }).catch(() => {});
  }
}



// ---------------- Configuration ----------------
const dashboard_url = "xxxxxxxxxxxxxxxxxx.fr";


// ---------------- Utilitaires ----------------

//récupère le user qui s'est connecté
function currentUser() {
  return sessionStorage.getItem("user").toLowerCase();
}

// Construit l'URL correcte /u/<user>/hostname (ou /hostname si pas de user)
function buildHostnameUrl() {
  const user = currentUser();
  const base = user ? `/u/${user}/hostname` : `/hostname`;
  return `${base}?nocache=${Date.now()}`;
}

// Fait une requête hostname et renvoie le texte 
function fetchHostnameOnce() {
  return fetch(buildHostnameUrl(), {
    cache: "no-store",
    headers: { "Connection": "close" }
  }).then(res => res.text());
}


function fetchHostname(){
   fetchHostnameOnce()
    .then(txt => { document.getElementById("hostname").innerText = txt; })
    .catch(() => { document.getElementById("hostname").innerText = "Erreur de récupération du hostname."; });
} 

// ---------------- fonctions ----------------
// Retourner au dashboard de l'utilisateur courant
function returnToDashboard() {
  const user = currentUser();
   if (user) {
   //ajoute flag leaving_for_dashboard pour ne pas arriver sur disconnect
    sessionStorage.setItem("leaving_for_dashboard", "1");
    window.open(`${dashboard_url}/u/${user}/dashboard`, "_self");
  } else {
    // si pas de session → retour à la page de login
    window.open(`${dashboard_url}/` ,"_self") ;
  }
}

//lance test de charge
 function runTest() {
  const resultDiv = document.getElementById("result");
  resultDiv.textContent = "Envoi de 500 requêtes en cours...";
  const counts = {};

// Array.from .... créé un tableau de 500 cases; la fonction fetch  (envoie une requete http vers app.demo) est envoyée 500 fois
//  Promise.all les exécute en parallèle et attend que toutes soient terminées avant d'afficher les résultats
   Promise.all(Array.from({ length: 500 }, () => fetchHostnameOnce()))    
    .then(results => {
      results.forEach(pod => { counts[pod] = (counts[pod] || 0) + 1; });
       // Affichage texte
      resultDiv.textContent = Object.entries(counts)
        .map(([pod, count]) => `${pod} : ${count} requêtes`)
        .join("\n");
        
    // Affichage graphique
      const ctx = document.getElementById('chart').getContext('2d');
        new Chart(ctx, {
          type: 'bar',
          data: {
            labels: Object.keys(counts),
            datasets: [{
              label: 'Nombre de requêtes',
              data: Object.values(counts),
              borderWidth: 1
            }]
          },
          options: {
            scales: {
              y: {
                beginAtZero: true,
                ticks: { precision: 0 }
              }
            }
          }
        });
      }).catch(() => {
        resultDiv.textContent = "❌ Erreur lors du test.";
      });
    }
  
  
//fonction de déconnexion sauvage fermeture fenêtre ou onglet
function registerDisconnectHandler(){

    //beforeunload = dernier événement déclenché avant fermeture de la page,rechargement ou navigation ailleurs. 
    // Préviens le dashboard (via /disconnect) de deconnexion brutale

    window.addEventListener("beforeunload", () => {
    const user = currentUser();
    const goingBack = sessionStorage.getItem("leaving_for_dashboard");

    if (!user)  {
     console.log ("aucun user en session ne rien faire")
    // si pas de user on ne fait rien
    }
    
    //*******************sinon si user***********************

    //vérifier si on quitte demo-app pour retourner sur le dashboard 
    else if (goingBack === "1"){
      console.log("retour vers dashboard : pas de disconnect envoyé");
      sessionStorage.removeItem("leaving_for_dashboard");
      // on ne fait pas de disconnecter
    }
    //sinon il se deconnecte si fermeture sauvage 
    else {
      const payload = JSON.stringify({ user });
    try {
      // Tentative  d'envoie à dashboard via sendBeacon à la fermeture brutale
      navigator.sendBeacon(`${dashboard_url}/disconnect`, payload);
    } 
    catch (e) {
    // Si sendBeacon n’est pas supporté (par certains navigateurs), on tente un fallback
      fetch(`${dashboard_url}/disconnect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
        keepalive: true
      }).catch(() => {});
    }
    }
  });
  
}

//****************Keep alive dashobard session pour gérer keep alive de dashboard lorsqu'on est sur demo-app*******************
// Intervalle d’envoi (30 secondes)
const KEEPALIVE_INTERVAL = 30000;

// Fonction d’envoi du signal au dashboard
function sendDashboardKeepAlive() {
  // Récupère le nom d'utilisateur depuis le local/session storage
  const user = currentUser();

  if (!user) {
   console.log ("aucun user en session ne rien faire")
    // si pas de user on ne fait rien
  }else{
  // Envoie une requête au dashboard principal pour maintenir la session
    fetch(`${dashboard_url}/keepAlive`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user }),
    keepalive: true // important pour permettre l’envoi même quand la page change
  }).catch(() => {
    // On ignore les erreurs réseau silencieusement
  });
}
}

  
//***************Lancement dès chargement de la page****************

// Lancement périodique du ping
setInterval(sendDashboardKeepAlive, KEEPALIVE_INTERVAL);

// Premier ping immédiat dès le chargement de la page
sendDashboardKeepAlive();

//Active la gestion de la deconnexion sauvage dès le chargement
registerDisconnectHandler();
