(function () {
  "use strict";

  document.querySelectorAll("form[data-jednom]").forEach(function (forma) {
    forma.addEventListener("submit", function () {
      forma.querySelector("button[type=submit]").disabled = true;
    });
  });

  var poljeLinka = document.getElementById("link-deljenja");
  if (poljeLinka) {
    var kopiraj = document.getElementById("kopiraj-link");
    var porukaKopiranja = document.getElementById("poruka-kopiranja");
    var oznaciLink = function () {
      poljeLinka.focus();
      poljeLinka.select();
    };
    poljeLinka.addEventListener("focus", oznaciLink);
    kopiraj.hidden = false;
    kopiraj.addEventListener("click", function () {
      var zapis = navigator.clipboard
        ? navigator.clipboard.writeText(poljeLinka.value)
        : Promise.reject(new Error("bez clipboard-a"));
      zapis
        .then(function () {
          porukaKopiranja.textContent = kopiraj.dataset.kopirano;
        })
        .catch(function () {
          oznaciLink();
          porukaKopiranja.textContent = kopiraj.dataset.oznaceno;
        });
    });
  }

  // Zvuk ishoda kruga. Podrazumevano je iskljucen; izbor igraca se pamti u ovom pregledacu.
  // Zavisi samo od statusa koji igrac vidi, pa uspeh i neuspeh koji se ne vidi zvuce isto.
  var KLJUC_ZVUKA = "orkestrator-zvuk";
  var dugmeZvuka = document.getElementById("zvuk");
  var zvukUkljucen = false;
  var audio = null;

  try {
    zvukUkljucen = window.localStorage.getItem(KLJUC_ZVUKA) === "da";
  } catch (greska) {
    zvukUkljucen = false;
  }

  function audioKontekst() {
    var Kontekst = window.AudioContext || window.webkitAudioContext;
    if (!Kontekst) {
      return null;
    }
    if (!audio) {
      audio = new Kontekst();
    }
    if (audio.state === "suspended") {
      audio.resume();
    }
    return audio;
  }

  // Tonovi: [frekvencija u Hz, pocetak u s, trajanje u s].
  var MELODIJE = {
    gotovo: { oblik: "sine", tonovi: [[523.25, 0, 0.16], [659.25, 0.1, 0.16], [783.99, 0.2, 0.3]] },
    dorada: { oblik: "triangle", tonovi: [[311.13, 0, 0.22], [233.08, 0.2, 0.4]] },
  };

  function pustiZvuk(gotovo) {
    if (!zvukUkljucen) {
      return;
    }
    var kontekst = audioKontekst();
    if (!kontekst) {
      return;
    }
    var melodija = gotovo ? MELODIJE.gotovo : MELODIJE.dorada;
    melodija.tonovi.forEach(function (ton) {
      var oscilator = kontekst.createOscillator();
      var jacina = kontekst.createGain();
      var pocetak = kontekst.currentTime + ton[1];
      var kraj = pocetak + ton[2];
      oscilator.type = melodija.oblik;
      oscilator.frequency.value = ton[0];
      jacina.gain.setValueAtTime(0.0001, pocetak);
      jacina.gain.exponentialRampToValueAtTime(0.2, pocetak + 0.02);
      jacina.gain.exponentialRampToValueAtTime(0.0001, kraj);
      oscilator.connect(jacina);
      jacina.connect(kontekst.destination);
      oscilator.start(pocetak);
      oscilator.stop(kraj + 0.05);
    });
  }

  if (dugmeZvuka) {
    dugmeZvuka.setAttribute("aria-pressed", String(zvukUkljucen));
    dugmeZvuka.hidden = false;
    dugmeZvuka.addEventListener("click", function () {
      zvukUkljucen = !zvukUkljucen;
      try {
        window.localStorage.setItem(KLJUC_ZVUKA, zvukUkljucen ? "da" : "ne");
      } catch (greska) {
        // Bez skladista izbor vazi do zatvaranja stranice.
      }
      dugmeZvuka.setAttribute("aria-pressed", String(zvukUkljucen));
      // Kratka potvrda da zvuk radi; klik je ujedno i dozvola pregledaca da pusti zvuk.
      pustiZvuk(true);
    });
  }

  var forma = document.getElementById("forma-poteza");
  if (!forma) {
    return;
  }

  var POLJA = ["model", "nivo", "kontekst", "podela"];
  // Tekstovi na izabranom jeziku dolaze iz sablona, pa skripta nema svoj tekst.
  var STATUS_GOTOVO = forma.dataset.statusGotovo;
  var MIN = forma.dataset.jedinicaMinuta;
  var potvrdi = document.getElementById("potvrdi");
  var porukaGreske = document.getElementById("greska-poteza");
  var token = forma.querySelector("input[name=csrfmiddlewaretoken]").value;
  var saljem = false;

  function izabrano(polje) {
    var izbor = forma.querySelector("input[name=" + polje + "]:checked");
    return izbor ? izbor.value : null;
  }

  function osveziDugme() {
    potvrdi.disabled = saljem || !POLJA.every(izabrano);
  }

  function postaviTekst(id, tekst) {
    document.getElementById(id).textContent = tekst;
  }

  function postaviStanje(id, tekst, prekoraceno) {
    var element = document.getElementById(id);
    element.textContent = tekst;
    element.classList.toggle("text-danger", prekoraceno);
  }

  var SVG = "http://www.w3.org/2000/svg";

  function ikona(oznaka, klasa) {
    var slika = document.createElementNS(SVG, "svg");
    var upotreba = document.createElementNS(SVG, "use");
    slika.setAttribute("class", klasa);
    slika.setAttribute("aria-hidden", "true");
    upotreba.setAttribute("href", "#" + oznaka);
    slika.appendChild(upotreba);
    return slika;
  }

  function oznakaIshoda(gotovo) {
    return gotovo ? "ik-gotovo" : "ik-dorada";
  }

  function postaviIshod(element, gotovo) {
    element.classList.toggle("ishod-gotovo", gotovo);
    element.classList.toggle("ishod-dorada", !gotovo);
  }

  // Merac prikazuje preostali deo budzeta ili roka; vrednost je vec izracunao server.
  function postaviMerilo(id, tekst) {
    var merilo = document.getElementById(id);
    var ukupno = Number(merilo.dataset.ukupno);
    var preostalo = Number(String(tekst).replace(",", "."));
    var udeo = Math.max(0, Math.min(100, (preostalo / ukupno) * 100));
    var punjenje = merilo.firstElementChild;
    punjenje.style.width = udeo + "%";
    punjenje.classList.toggle("merilo-nisko", udeo < 25);
  }

  function dodajUIstoriju(naziv, odgovor) {
    var gotovo = odgovor.status === STATUS_GOTOVO;
    var red = document.createElement("li");
    var tekst = document.createElement("span");
    var prvi = document.createElement("span");
    var drugi = document.createElement("span");
    postaviIshod(red, gotovo);
    tekst.className = "istorija-tekst";
    prvi.className = "istorija-naziv";
    prvi.textContent = odgovor.krug + ". " + naziv;
    drugi.className = "istorija-podaci";
    drugi.textContent = odgovor.status + " · " + odgovor.cena + " $ · " + odgovor.minuti + " " + MIN;
    tekst.appendChild(prvi);
    tekst.appendChild(drugi);
    red.appendChild(ikona("ik-zadatak-" + odgovor.krug, "istorija-znak"));
    red.appendChild(tekst);
    red.appendChild(ikona(oznakaIshoda(gotovo), "istorija-ishod"));
    document.getElementById("istorija").appendChild(red);
    document.getElementById("panel-istorije").hidden = false;
  }

  function postaviSegmente(odgovor, gotovo) {
    var segmenti = document.querySelectorAll(".segment");
    var odigran = segmenti[odgovor.krug - 1];
    odigran.classList.remove("segment-tekuci");
    odigran.classList.add("segment-odigran", gotovo ? "segment-gotovo" : "segment-dorada");
    if (odgovor.sledeci) {
      segmenti[odgovor.sledeci.krug - 1].classList.add("segment-tekuci");
    }
  }

  function prikaziRezultat(odgovor) {
    var nazivZadatka = document.getElementById("naziv-zadatka").textContent;
    var status = document.getElementById("poslednji-status");
    var gotovo = odgovor.status === STATUS_GOTOVO;

    status.textContent = odgovor.status;
    status.classList.toggle("status-gotovo", gotovo);
    status.classList.toggle("status-dorada", !gotovo);
    postaviTekst("poslednja-cena", odgovor.cena);
    postaviTekst("poslednji-minuti", odgovor.minuti);
    document.getElementById("ikona-ishoda").setAttribute("href", "#" + oznakaIshoda(gotovo));
    postaviIshod(document.getElementById("rezultat-poteza"), gotovo);
    document.getElementById("rezultat-poteza").hidden = false;
    pustiZvuk(gotovo);

    postaviStanje("budzet", odgovor.budzet_preostalo, odgovor.budzet_prekoracen);
    postaviStanje("rok", odgovor.rok_preostalo, odgovor.rok_prekoracen);
    postaviMerilo("merilo-budzeta", odgovor.budzet_preostalo);
    postaviMerilo("merilo-roka", odgovor.rok_preostalo);
    postaviSegmente(odgovor, gotovo);
    dodajUIstoriju(nazivZadatka, odgovor);

    if (odgovor.zavrsena) {
      forma.hidden = true;
      document.getElementById("zaglavlje-zadatka").hidden = true;
      document.getElementById("kraj-partije").hidden = false;
      return;
    }

    forma.dataset.krug = odgovor.sledeci.krug;
    postaviTekst("broj-kruga", odgovor.sledeci.krug);
    postaviTekst("naziv-zadatka", odgovor.sledeci.naziv);
    document.getElementById("ikona-zadatka").setAttribute("href", "#ik-zadatak-" + odgovor.sledeci.krug);
    forma.reset();
  }

  function prikaziGresku() {
    porukaGreske.textContent = forma.dataset.porukaGreske;
    porukaGreske.hidden = false;
  }

  function posaljiPotez() {
    var telo = { krug: Number(forma.dataset.krug) };
    POLJA.forEach(function (polje) {
      telo[polje] = izabrano(polje);
    });

    return fetch(forma.dataset.adresa, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": token },
      body: JSON.stringify(telo),
    }).then(function (odgovor) {
      if (odgovor.status === 409) {
        window.location.reload();
        return;
      }
      if (!odgovor.ok) {
        prikaziGresku();
        return;
      }
      return odgovor.json().then(prikaziRezultat);
    });
  }

  forma.addEventListener("change", osveziDugme);

  forma.addEventListener("submit", function (dogadjaj) {
    dogadjaj.preventDefault();
    if (saljem || !POLJA.every(izabrano)) {
      return;
    }
    saljem = true;
    osveziDugme();
    porukaGreske.hidden = true;
    posaljiPotez()
      .catch(prikaziGresku)
      .finally(function () {
        saljem = false;
        osveziDugme();
      });
  });
})();
