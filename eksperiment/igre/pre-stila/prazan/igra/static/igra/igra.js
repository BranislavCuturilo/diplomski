(function () {
  "use strict";

  document.querySelectorAll("form[data-jednom]").forEach(function (forma) {
    forma.addEventListener("submit", function () {
      forma.querySelector("button[type=submit]").disabled = true;
    });
  });

  var forma = document.getElementById("forma-poteza");
  if (!forma) {
    return;
  }

  var POLJA = ["model", "nivo", "kontekst", "podela"];
  var STATUS_GOTOVO = "готово";
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

  function dodajUIstoriju(naziv, odgovor) {
    var red = document.createElement("li");
    var prvi = document.createElement("span");
    var drugi = document.createElement("span");
    prvi.className = "istorija-naziv";
    prvi.textContent = odgovor.krug + ". " + naziv;
    drugi.className = "istorija-podaci";
    drugi.textContent = odgovor.status + " · " + odgovor.cena + " $ · " + odgovor.minuti + " мин";
    red.appendChild(prvi);
    red.appendChild(drugi);
    document.getElementById("istorija").appendChild(red);
    document.getElementById("panel-istorije").hidden = false;
  }

  function prikaziRezultat(odgovor) {
    var nazivZadatka = document.getElementById("naziv-zadatka").textContent;
    var status = document.getElementById("poslednji-status");

    status.textContent = odgovor.status;
    status.classList.toggle("status-gotovo", odgovor.status === STATUS_GOTOVO);
    status.classList.toggle("status-dorada", odgovor.status !== STATUS_GOTOVO);
    postaviTekst("poslednja-cena", odgovor.cena);
    postaviTekst("poslednji-minuti", odgovor.minuti);
    document.getElementById("rezultat-poteza").hidden = false;

    postaviStanje("budzet", odgovor.budzet_preostalo, odgovor.budzet_prekoracen);
    postaviStanje("rok", odgovor.rok_preostalo, odgovor.rok_prekoracen);
    document.querySelectorAll(".segment")[odgovor.krug - 1].classList.add("segment-odigran");
    dodajUIstoriju(nazivZadatka, odgovor);

    if (odgovor.zavrsena) {
      forma.hidden = true;
      document.getElementById("naziv-zadatka").hidden = true;
      document.querySelector("#panel-poteza .oznaka-zadatka").hidden = true;
      document.getElementById("kraj-partije").hidden = false;
      return;
    }

    forma.dataset.krug = odgovor.sledeci.krug;
    postaviTekst("broj-kruga", odgovor.sledeci.krug);
    postaviTekst("naziv-zadatka", odgovor.sledeci.naziv);
    forma.reset();
  }

  function prikaziGresku() {
    porukaGreske.textContent = "Потез није прихваћен. Покушај поново.";
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
