(function () {
  "use strict";

  const IMENA_IZBORA = ["model", "nivo", "kontekst", "podela"];
  const STATUS_DORADA = "враћено на дораду";
  const PITANJE_NOVA = "Започети нову игру? Текућа партија се губи.";
  const PORUKE = {
    osvezeno: "Стање је освежено.",
    nemaIgre: "Партија више не постоји. Освежите страну за нову игру.",
    neispravno: "Захтев није исправан. Освежите страну.",
    server: "Сервер није одговорио како треба. Покушајте поново.",
    stanje: "Стање игре није могло да се прочита. Освежите страну.",
  };

  const el = {
    stanje: document.getElementById("stanje-igre"),
    kontrole: document.getElementById("kontrole"),
    potvrdi: document.getElementById("potvrdi"),
    procena: document.getElementById("procena"),
    rezultat: document.getElementById("rezultat"),
    poruka: document.getElementById("poruka"),
    krug: document.getElementById("krug"),
    zadatak: document.getElementById("zadatak"),
    budzet: document.getElementById("budzet"),
    rok: document.getElementById("rok"),
    zavrsni: document.getElementById("zavrsni"),
    nova: document.getElementById("nova-forma"),
    sablonTiha: document.getElementById("sablon-tiha"),
    sablonLekcija: document.getElementById("sablon-lekcija"),
  };

  let trenutno = null;
  let prethodniKrug = null;
  let uToku = false;

  function mesto(roditelj, ime) {
    return roditelj.querySelector('[data-mesto="' + ime + '"]');
  }

  function broj(vrednost, decimale) {
    let tekst = Number(vrednost).toFixed(decimale);
    if (Number(tekst) === 0) {
      tekst = (0).toFixed(decimale);
    }
    return tekst.replace(".", ",");
  }

  function dolari(vrednost, decimale) {
    return broj(vrednost, decimale) + " $";
  }

  function minuti(vrednost) {
    return broj(vrednost, 1) + " мин";
  }

  function radio(ime) {
    return document.querySelectorAll('input[name="' + ime + '"]');
  }

  function izabrano() {
    const izbori = {};
    for (const ime of IMENA_IZBORA) {
      const oznaceno = document.querySelector('input[name="' + ime + '"]:checked');
      if (!oznaceno) {
        return null;
      }
      izbori[ime] = oznaceno.value;
    }
    return izbori;
  }

  function poruka(tekst, vrsta) {
    if (!tekst) {
      el.poruka.hidden = true;
      el.poruka.textContent = "";
      return;
    }
    el.poruka.classList.remove("alert-info", "alert-danger");
    el.poruka.classList.add(vrsta === "greska" ? "alert-danger" : "alert-info");
    el.poruka.textContent = tekst;
    el.poruka.hidden = false;
  }

  function nacrtajMeru(kontejner, mera, decimale, format) {
    mesto(kontejner, "potroseno").textContent = format(mera.potroseno, decimale);
    mesto(kontejner, "preostalo").textContent = format(mera.preostalo, decimale);
    const traka = mesto(kontejner, "traka");
    const procenat = mera.limit > 0 ? Math.min(100, Math.max(0, (mera.potroseno / mera.limit) * 100)) : 0;
    traka.style.width = procenat + "%";
    traka.classList.toggle("bg-danger", mera.preostalo < 0);
    const pb = kontejner.querySelector(".progress");
    pb.setAttribute("aria-valuenow", String(Math.round(procenat)));
  }

  function nacrtajProcenu(stanje) {
    if (stanje.faza !== "igra" || !stanje.procene) {
      el.procena.textContent = "";
      return;
    }
    const izbori = izabrano();
    if (!izbori) {
      el.procena.textContent = "Изаберите све четири опције да видите процену.";
      return;
    }
    const kljuc = IMENA_IZBORA.map(function (ime) { return izbori[ime]; }).join("|");
    const p = stanje.procene[kljuc];
    if (!p) {
      el.procena.textContent = "";
      return;
    }
    el.procena.textContent = "Процена: цена " + dolari(p.cena, 3) + ", " + minuti(p.minuti) + ".";
  }

  function nacrtajDugme() {
    const faza = trenutno && trenutno.faza;
    el.potvrdi.disabled = uToku || faza !== "igra" || izabrano() === null;
  }

  function nacrtajRezultat(poslednji) {
    if (!poslednji) {
      el.rezultat.hidden = true;
      return;
    }
    mesto(el.rezultat, "zadatak").textContent = "Круг " + poslednji.krug + ": " + poslednji.zadatak;
    mesto(el.rezultat, "cena").textContent = dolari(poslednji.cena, 3);
    mesto(el.rezultat, "minuti").textContent = minuti(poslednji.minuti);
    mesto(el.rezultat, "status").textContent = poslednji.status;
    const dorada = poslednji.status === STATUS_DORADA;
    el.rezultat.classList.toggle("alert-warning", dorada);
    el.rezultat.classList.toggle("alert-success", !dorada);
    el.rezultat.hidden = false;
  }

  function nacrtajZavrsni(zavrsni) {
    if (!zavrsni) {
      el.zavrsni.hidden = true;
      return;
    }
    mesto(el.zavrsni, "poeni").textContent = String(zavrsni.poeni);
    mesto(el.zavrsni, "ocena").textContent = zavrsni.ocena;
    mesto(el.zavrsni, "cena").textContent = dolari(zavrsni.ukupna_cena, 2);
    mesto(el.zavrsni, "minuti").textContent = minuti(zavrsni.ukupni_minuti);
    mesto(el.zavrsni, "budzet-prekoracen").hidden = !zavrsni.budzet_prekoracen;
    mesto(el.zavrsni, "rok-prekoracen").hidden = !zavrsni.rok_prekoracen;

    const tihe = mesto(el.zavrsni, "tihe");
    tihe.replaceChildren();
    for (const t of zavrsni.tihe_greske) {
      const red = el.sablonTiha.content.firstElementChild.cloneNode(true);
      mesto(red, "tekst").textContent =
        "Круг " + t.krug + ": " + t.zadatak +
        " (додатак: " + dolari(t.dodatak_cena, 2) + ", " + minuti(t.dodatak_minuti) + ")";
      tihe.appendChild(red);
    }
    tihe.hidden = zavrsni.tihe_greske.length === 0;
    mesto(el.zavrsni, "nema-tihih").hidden = zavrsni.tihe_greske.length !== 0;

    const lekcije = mesto(el.zavrsni, "lekcije");
    lekcije.replaceChildren();
    for (const l of zavrsni.lekcije) {
      const red = el.sablonLekcija.content.firstElementChild.cloneNode(true);
      mesto(red, "tekst").textContent = l.tekst;
      mesto(red, "odeljak").textContent = "(одељак " + l.odeljak + ")";
      lekcije.appendChild(red);
    }
    mesto(el.zavrsni, "lekcije-blok").hidden = zavrsni.lekcije.length === 0;

    mesto(el.zavrsni, "napomena").textContent = zavrsni.napomena;
    el.zavrsni.hidden = false;
  }

  function prikazi(stanje) {
    trenutno = stanje;
    const igra = stanje.faza === "igra";

    if (igra) {
      el.krug.textContent = "Круг " + stanje.krug + " од " + stanje.ukupno_krugova;
    } else {
      el.krug.textContent = "Игра је завршена";
    }

    nacrtajMeru(el.budzet, stanje.budzet, 2, dolari);
    nacrtajMeru(el.rok, stanje.rok, 1, function (v, d) { return broj(v, d) + " мин"; });

    el.kontrole.hidden = !igra;
    if (igra) {
      el.zadatak.textContent = stanje.zadatak.naziv;
    }
    if (stanje.krug !== prethodniKrug) {
      for (const ime of IMENA_IZBORA) {
        for (const r of radio(ime)) {
          r.checked = false;
        }
      }
      prethodniKrug = stanje.krug;
    }

    nacrtajProcenu(stanje);
    nacrtajRezultat(stanje.poslednji);
    nacrtajZavrsni(stanje.zavrsni);
    nacrtajDugme();
  }

  function procitajKolacic(ime) {
    const delovi = document.cookie ? document.cookie.split("; ") : [];
    for (const deo of delovi) {
      const i = deo.indexOf("=");
      if (i > -1 && deo.slice(0, i) === ime) {
        return decodeURIComponent(deo.slice(i + 1));
      }
    }
    return "";
  }

  function jeObjekat(x) {
    return x !== null && typeof x === "object" && !Array.isArray(x);
  }

  async function posalji() {
    if (uToku || !trenutno || trenutno.faza !== "igra") {
      return;
    }
    const izbori = izabrano();
    if (!izbori) {
      return;
    }
    uToku = true;
    nacrtajDugme();
    try {
      const odgovor = await fetch(el.kontrole.dataset.urlPotez, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": procitajKolacic("csrftoken"),
        },
        body: JSON.stringify({ krug: trenutno.krug, izbori: izbori }),
      });
      const tekst = await odgovor.text();
      let telo = null;
      try {
        telo = JSON.parse(tekst);
      } catch (e) {
        telo = null;
      }

      if (odgovor.status === 200 && jeObjekat(telo) && telo.faza) {
        poruka("");
        prikazi(telo);
      } else if (odgovor.status === 409 && jeObjekat(telo) && jeObjekat(telo.stanje)) {
        prikazi(telo.stanje);
        poruka(PORUKE.osvezeno, "info");
      } else if (odgovor.status === 409 && jeObjekat(telo) && telo.greska === "nema_igre") {
        poruka(PORUKE.nemaIgre, "greska");
      } else if (odgovor.status === 400) {
        poruka(PORUKE.neispravno, "greska");
      } else {
        poruka(PORUKE.server, "greska");
      }
    } catch (e) {
      poruka(PORUKE.server, "greska");
    } finally {
      uToku = false;
      nacrtajDugme();
      window.scrollTo({ top: 0 });
    }
  }

  function pokreni() {
    el.nova.addEventListener("submit", function (dogadjaj) {
      if (trenutno && trenutno.faza === "igra" && !window.confirm(PITANJE_NOVA)) {
        dogadjaj.preventDefault();
      }
    });

    let pocetno = null;
    try {
      pocetno = JSON.parse(el.stanje.textContent);
    } catch (e) {
      pocetno = null;
    }
    if (!jeObjekat(pocetno)) {
      poruka(PORUKE.stanje, "greska");
      return;
    }

    el.kontrole.addEventListener("change", function () {
      if (trenutno) {
        nacrtajProcenu(trenutno);
      }
      nacrtajDugme();
    });
    el.potvrdi.addEventListener("click", posalji);
    prikazi(pocetno);
  }

  pokreni();
})();
