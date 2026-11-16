(function () {
  "use strict";

  // Skripta nema ni jedno slovo teksta za ekran: sav tekst stize iz json_script "tekstovi" (jezik bira server),
  // a stanje i ocene stizu kao kljucevi ("dorada", "odlican", "crud"...). Tekst se upisuje samo kroz textContent.
  const IMENA_IZBORA = ["model", "nivo", "kontekst", "podela"];
  const KLJUC_DORADA = "dorada";

  // Samo izgled: kljuc ocene bira ikonu i boju zavrsnog ekrana.
  const IZGLED_OCENE = {
    odlican: { ikona: "oc-odlican", ton: "odlican" },
    solidan: { ikona: "oc-solidan", ton: "solidan" },
    skup: { ikona: "oc-skup", ton: "skup" },
    pozar: { ikona: "oc-pozar", ton: "pozar" },
  };
  const BLIZU_GRANICE = 85;

  const el = {
    stanje: document.getElementById("stanje-igre"),
    tekstovi: document.getElementById("tekstovi"),
    tekstoviGreska: document.getElementById("tekstovi-greska"),
    staza: document.getElementById("staza"),
    slika: document.querySelector('#kontrole [data-mesto="slika"]'),
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
    rangPodaci: document.getElementById("rang-lista"),
    rangForma: document.getElementById("rang-forma"),
    rangIme: document.getElementById("rang-ime"),
    rangSacuvaj: document.getElementById("rang-sacuvaj"),
    rangGreska: document.getElementById("rang-greska"),
    rangPoruka: document.getElementById("rang-poruka"),
    rang: document.getElementById("rang"),
    rangTabela: document.getElementById("rang-tabela"),
    rangRedovi: document.getElementById("rang-redovi"),
    rangPrazno: document.getElementById("rang-prazno"),
    rangLegenda: document.getElementById("rang-legenda"),
    sablonRangRed: document.getElementById("sablon-rang-red"),
    // json_script "rang-dana" nosi podatke; sekcija ima drugi id, jer id mora biti jedinstven.
    rangDanaPodaci: document.getElementById("rang-dana"),
    rangDana: document.getElementById("rang-dana-sekcija"),
    rangDanaTabela: document.getElementById("rang-dana-tabela"),
    rangDanaRedovi: document.getElementById("rang-dana-redovi"),
    rangDanaPrazno: document.getElementById("rang-dana-prazno"),
    deli: document.getElementById("deli"),
    deliDugme: document.getElementById("deli-dugme"),
    deliBlok: document.getElementById("deli-blok"),
    deliLink: document.getElementById("deli-link"),
    deliRok: document.getElementById("deli-rok"),
    deliKopiraj: document.getElementById("deli-kopiraj"),
    zvukDugme: document.getElementById("zvuk-dugme"),
    deliPosalji: document.getElementById("deli-posalji"),
    deliPoruka: document.getElementById("deli-poruka"),
    deljeniRezultat: document.getElementById("deljeni-rezultat"),
    deljeniPodaci: document.getElementById("deljeno-podaci"),
    deljenoImeRed: document.getElementById("deljeno-ime-red"),
    deljenoIme: document.getElementById("deljeno-ime"),
    deljenoDatum: document.getElementById("deljeno-datum"),
  };

  // Tekstovi u jeziku strane (T) postavlja pokreni(); bez njih skripta ne radi nista.
  let T = null;
  let trenutno = null;
  let prethodniKrug = null;
  let uToku = false;
  // Cuvanje rezultata ima svoju zastitu, odvojenu od uToku (potez).
  let uCuvanju = false;
  // Poslednja procitana rang lista (ili null ako nije procitana) i znak da je ova partija sacuvana.
  let rang = null;
  let sacuvanoOvde = false;
  // Posle 409 forma se skriva i kada rang ne kaze da je sacuvano.
  let formaZatvorena = false;
  // Deljenje ima svoju zastitu, odvojenu od uToku i uCuvanju; uSlanju sprecava drugi navigator.share dok je prvi otvoren.
  let uDeljenju = false;
  let uSlanju = false;
  // Prijava imena: jedna zastita za obe liste, i oznake redova prijavljenih sa ove strane (do ponovnog ucitavanja).
  let uPrijavi = false;
  const prijavljeniRedovi = new Set();

  function mesto(roditelj, ime) {
    return roditelj.querySelector('[data-mesto="' + ime + '"]');
  }

  function jeObjekat(x) {
    return x !== null && typeof x === "object" && !Array.isArray(x);
  }

  function ima(mapa, kljuc) {
    return jeObjekat(mapa) && typeof kljuc === "string" && Object.prototype.hasOwnProperty.call(mapa, kljuc);
  }

  // ---------- Tekstovi ----------

  // Tekst po kljucu iz mape grupe; nepoznat kljuc daje sam kljuc, pa je kvar vidljiv (i hvata ga test).
  function prevod(grupa, kljuc) {
    const mapa = T[grupa];
    if (ima(mapa, kljuc) && typeof mapa[kljuc] === "string") {
      return mapa[kljuc];
    }
    return String(kljuc);
  }

  function poruke(ime) {
    return prevod("poruke", ime);
  }

  // Menja %(ime)s vrednoscu; mesto bez vrednosti ostaje vidljivo.
  function zameni(obrazac, vrednosti) {
    return String(obrazac).replace(/%\(([A-Za-z0-9_]+)\)s/g, function (celo, ime) {
      return ima(vrednosti, ime) ? String(vrednosti[ime]) : celo;
    });
  }

  function obrazac(ime, vrednosti) {
    return zameni(prevod("obrasci", ime), vrednosti);
  }

  function jeTekst(x) {
    return typeof x === "string";
  }

  function jeMapaTeksta(x) {
    return jeObjekat(x) && Object.keys(x).every(function (k) { return jeTekst(x[k]); });
  }

  // Oblik mape tekstova; sve sto nije po ugovoru je neuspeh (strana pokazuje #tekstovi-greska).
  function procitajTekstove() {
    if (!el.tekstovi) {
      return null;
    }
    let t = null;
    try {
      t = JSON.parse(el.tekstovi.textContent);
    } catch (e) {
      return null;
    }
    const grupe = ["zadaci", "status", "ocene", "lekcije", "poruke", "obrasci", "format"];
    if (!jeObjekat(t) || !grupe.every(function (g) { return jeMapaTeksta(t[g]); })) {
      return null;
    }
    if (!jeTekst(t.napomena) || !jeTekst(t.pitanjeNova) || !jeMapaTeksta(t.deljenje)) {
      return null;
    }
    return t;
  }

  function tekstoviNisuProcitani() {
    if (el.tekstoviGreska) {
      el.tekstoviGreska.hidden = false;
    }
  }

  // ---------- Brojevi ----------

  // Zarez, novac i minuti idu po jeziku strane iz T.format; bez Intl i toLocaleString (jezik pregledaca nije jezik strane).
  function iznos(vrednost, decimale, obrazacFormata) {
    let tekst = Number(vrednost).toFixed(decimale);
    if (Number(tekst) === 0) {
      tekst = (0).toFixed(decimale);
    }
    let predznak = "";
    if (tekst.charAt(0) === "-") {
      predznak = "-";
      tekst = tekst.slice(1);
    }
    tekst = tekst.replace(".", function () { return T.format.zarez; });
    return predznak + zameni(obrazacFormata, { iznos: tekst });
  }

  function dolari(vrednost, decimale) {
    return iznos(vrednost, decimale, T.format.novac);
  }

  function minuti(vrednost, decimale) {
    return iznos(vrednost, decimale === undefined ? 1 : decimale, T.format.minuti);
  }

  // Izgled: ikona se menja samo preko atributa href na <use>, nikad kroz innerHTML.
  function ikona(svg, id) {
    const use = svg ? svg.querySelector("use") : null;
    if (use) {
      use.setAttribute("href", "#" + id);
    }
  }

  // Izgled: staza zadataka; redni broj kruga je javan, pa tacke ne odaju nista drugo.
  function nacrtajStazu(tekuci) {
    if (!el.staza) {
      return;
    }
    el.staza.querySelectorAll("li").forEach(function (tacka, i) {
      tacka.classList.toggle("je-prosao", i + 1 < tekuci);
      tacka.classList.toggle("je-tu", i + 1 === tekuci);
    });
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
    if (!el.poruka) {
      return;
    }
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

    // Izgled: granica, upozorenje i stanje kartice (bez boje kao jedinog znaka: ikona i pruge).
    const prekoraceno = mera.preostalo < 0;
    mesto(kontejner, "granica").textContent = format(mera.limit, decimale);
    mesto(kontejner, "upozorenje").hidden = !prekoraceno;
    kontejner.classList.toggle("je-prekoraceno", prekoraceno);
    kontejner.classList.toggle("je-blizu", !prekoraceno && procenat >= BLIZU_GRANICE);
  }

  function nacrtajProcenu(stanje) {
    if (stanje.faza !== "igra" || !stanje.procene) {
      el.procena.textContent = "";
      return;
    }
    const izbori = izabrano();
    if (!izbori) {
      el.procena.textContent = poruke("izaberite");
      return;
    }
    const kljuc = IMENA_IZBORA.map(function (ime) { return izbori[ime]; }).join("|");
    const p = stanje.procene[kljuc];
    if (!p) {
      el.procena.textContent = "";
      return;
    }
    el.procena.textContent = obrazac("procena", { cena: dolari(p.cena, 3), minuti: minuti(p.minuti) });
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
    mesto(el.rezultat, "zadatak").textContent =
      obrazac("rezultatKruga", { krug: poslednji.krug, zadatak: prevod("zadaci", poslednji.zadatak) });
    mesto(el.rezultat, "cena").textContent = dolari(poslednji.cena, 3);
    mesto(el.rezultat, "minuti").textContent = minuti(poslednji.minuti);
    mesto(el.rezultat, "status").textContent = prevod("status", poslednji.status);
    const dorada = poslednji.status === KLJUC_DORADA;
    el.rezultat.classList.toggle("alert-warning", dorada);
    el.rezultat.classList.toggle("alert-success", !dorada);
    ikona(mesto(el.rezultat, "status-ikona"), dorada ? "ish-dorada" : "ish-gotovo");
    el.rezultat.hidden = false;
    // Izgled: kratko isticanje (220 ms); sadrzaj je vec u DOM-u, animacija ga ne odlaze.
    el.rezultat.classList.remove("ulaz");
    void el.rezultat.offsetWidth;
    el.rezultat.classList.add("ulaz");
  }

  // Recenica sa iznosom kazne samo kad je budzet prekoracen, oba broja postoje i mapa ima kaznu;
  // inace null, pa ostaje postojeca recenica (stari snimci i stare sesije nemaju brojeve).
  function tekstKazneBudzeta(zavrsni) {
    const procenat = zavrsni.budzet_procenat;
    const kazna = zavrsni.kazna_budzet;
    if (!zavrsni.budzet_prekoracen || !Number.isInteger(procenat) || !Number.isInteger(kazna)) {
      return null;
    }
    if (!ima(T.budzetKazne, String(kazna)) || !jeTekst(T.budzetKazne[String(kazna)]) || !jeTekst(T.format.procenat)) {
      return null;
    }
    return zameni(T.budzetKazne[String(kazna)], {
      procenat: zameni(T.format.procenat, { iznos: String(procenat) }),
    });
  }

  function nacrtajBudzet(zavrsni) {
    const blok = mesto(el.zavrsni, "budzet-prekoracen");
    const osnovno = mesto(blok, "budzet-osnovno");
    const iznosMesto = mesto(blok, "budzet-iznos");
    const tekst = tekstKazneBudzeta(zavrsni);
    blok.hidden = !zavrsni.budzet_prekoracen;
    iznosMesto.textContent = tekst === null ? "" : tekst;
    iznosMesto.hidden = tekst === null;
    osnovno.hidden = tekst !== null;
  }

  function nacrtajZavrsni(zavrsni) {
    if (!zavrsni) {
      el.zavrsni.hidden = true;
      return;
    }
    mesto(el.zavrsni, "poeni").textContent = String(zavrsni.poeni);
    mesto(el.zavrsni, "ocena").textContent = prevod("ocene", zavrsni.ocena);
    const izgledOcene = ima(IZGLED_OCENE, zavrsni.ocena) ? IZGLED_OCENE[zavrsni.ocena] : null;
    ikona(mesto(el.zavrsni, "ocena-ikona"), izgledOcene ? izgledOcene.ikona : "oc-solidan");
    el.zavrsni.setAttribute("data-ocena", izgledOcene ? izgledOcene.ton : "solidan");
    el.zavrsni.style.setProperty("--poeni", String(Math.min(100, Math.max(0, Number(zavrsni.poeni)))));
    mesto(el.zavrsni, "cena").textContent = dolari(zavrsni.ukupna_cena, 2);
    mesto(el.zavrsni, "minuti").textContent = minuti(zavrsni.ukupni_minuti);
    nacrtajBudzet(zavrsni);
    mesto(el.zavrsni, "rok-prekoracen").hidden = !zavrsni.rok_prekoracen;

    const tihe = mesto(el.zavrsni, "tihe");
    tihe.replaceChildren();
    for (const t of zavrsni.tihe_greske) {
      const red = el.sablonTiha.content.firstElementChild.cloneNode(true);
      mesto(red, "tekst").textContent = obrazac("tiha", {
        krug: t.krug,
        zadatak: prevod("zadaci", t.zadatak),
        cena: dolari(t.dodatak_cena, 2),
        minuti: minuti(t.dodatak_minuti),
      });
      tihe.appendChild(red);
    }
    tihe.hidden = zavrsni.tihe_greske.length === 0;
    mesto(el.zavrsni, "nema-tihih").hidden = zavrsni.tihe_greske.length !== 0;

    const lekcije = mesto(el.zavrsni, "lekcije");
    lekcije.replaceChildren();
    for (const l of zavrsni.lekcije) {
      const red = el.sablonLekcija.content.firstElementChild.cloneNode(true);
      mesto(red, "tekst").textContent = prevod("lekcije", l.oznaka);
      mesto(red, "odeljak").textContent = obrazac("odeljak", { odeljak: l.odeljak });
      lekcije.appendChild(red);
    }
    mesto(el.zavrsni, "lekcije-blok").hidden = zavrsni.lekcije.length === 0;

    mesto(el.zavrsni, "napomena").textContent = T.napomena;
    el.zavrsni.hidden = false;
  }

  function prikazi(stanje) {
    trenutno = stanje;
    const igra = stanje.faza === "igra";

    if (igra) {
      el.krug.textContent = obrazac("krug", { krug: stanje.krug, ukupno: stanje.ukupno_krugova });
    } else {
      el.krug.textContent = prevod("obrasci", "zavrsena");
    }

    nacrtajMeru(el.budzet, stanje.budzet, 2, dolari);
    nacrtajMeru(el.rok, stanje.rok, 1, minuti);

    el.kontrole.hidden = !igra;
    if (igra) {
      el.zadatak.textContent = prevod("zadaci", stanje.zadatak);
      ikona(el.slika, "zad-" + stanje.krug);
    }
    nacrtajStazu(igra ? stanje.krug : stanje.ukupno_krugova + 1);
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

  // Odgovor se cita kao tekst, pa tek onda kao JSON: 403 i 500 su HTML strane, pa telo je tada null.
  async function procitajOdgovor(odgovor) {
    const tekst = await odgovor.text();
    try {
      return JSON.parse(tekst);
    } catch (e) {
      return null;
    }
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
    if (zvukUkljucen) {
      // Klik na potez je radnja igraca: tu se pravi i budi AudioContext, pre fetch-a.
      zvukPripremi();
    }
    try {
      const odgovor = await fetch(el.kontrole.dataset.urlPotez, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": procitajKolacic("csrftoken"),
        },
        body: JSON.stringify({ krug: trenutno.krug, izbori: izbori }),
      });
      const telo = await procitajOdgovor(odgovor);

      if (odgovor.status === 200 && jeObjekat(telo) && telo.faza) {
        poruka("");
        prikazi(telo);
        // Zvuk samo posle uspesnog odgovora (200); samo status poslednjeg kruga, nista drugo iz odgovora.
        zvukIshoda(jeObjekat(telo.poslednji) ? telo.poslednji.status : null);
      } else if (odgovor.status === 409 && jeObjekat(telo) && jeObjekat(telo.stanje)) {
        prikazi(telo.stanje);
        poruka(poruke("osvezeno"), "info");
      } else if (odgovor.status === 409 && jeObjekat(telo) && telo.greska === "nema_igre") {
        poruka(poruke("nemaIgre"), "greska");
      } else if (odgovor.status === 400) {
        poruka(poruke("neispravno"), "greska");
      } else {
        poruka(poruke("server"), "greska");
      }
    } catch (e) {
      poruka(poruke("server"), "greska");
    } finally {
      uToku = false;
      nacrtajDugme();
      window.scrollTo({ top: 0 });
    }
  }

  // ---------- Zvuk ishoda kruga ----------
  // Kratki tonovi iz Web Audio API-ja (oscilator + envelope), bez datoteka. Izbor igraca je u localStorage ("1"/"0",
  // podrazumevano iskljuceno); server ga ne zna. Svako citanje i pisanje skladista je u try/catch: bez skladista
  // prekidac radi do zatvaranja strane.
  const KLJUC_ZVUKA = "orkestrator.zvuk";
  const KLJUC_GOTOVO = "gotovo";
  // Dva tona: [frekvencija u Hz, trajanje u s]. Gotovo je uzlazno i svetlo, dorada silazno i duboko.
  const TONOVI = {
    gotovo: { oblik: "sine", niz: [[660, 0.12], [880, 0.2]] },
    dorada: { oblik: "triangle", niz: [[330, 0.14], [247, 0.26]] },
  };
  let zvukUkljucen = false;
  let zvukKontekst = null;

  function webAudio() {
    return window.AudioContext || window.webkitAudioContext || null;
  }

  function procitajZvuk() {
    try {
      return window.localStorage.getItem(KLJUC_ZVUKA) === "1";
    } catch (e) {
      // Skladiste moze biti zabranjeno (privatni rezim, politika): izbor tada traje do zatvaranja strane.
      return false;
    }
  }

  function upisiZvuk(ukljucen) {
    try {
      window.localStorage.setItem(KLJUC_ZVUKA, ukljucen ? "1" : "0");
    } catch (e) {
      // Bez skladista izbor se ne pamti posle ove strane; prekidac i dalje radi, pa greske nema.
    }
  }

  // Poziva se samo iz radnje igraca (klik na prekidac ili na potez): pregledac inace ne pusta zvuk.
  function zvukPripremi() {
    const Kontekst = webAudio();
    if (!Kontekst) {
      return null;
    }
    try {
      if (zvukKontekst === null) {
        zvukKontekst = new Kontekst();
      }
      if (zvukKontekst.state === "suspended" && typeof zvukKontekst.resume === "function") {
        const obecanje = zvukKontekst.resume();
        if (obecanje && typeof obecanje.catch === "function") {
          obecanje.catch(function () { /* pregledac odbio zvuk: igra ide dalje bez njega */ });
        }
      }
    } catch (e) {
      // Zvuk je dodatak: kvar Web Audio-a nikad ne sme da zaustavi potez.
      return null;
    }
    return zvukKontekst;
  }

  // PRAVILO IGRE (projekat-domen, pravilo 1): uspeh i tih neuspeh moraju zvucati POTPUNO isto. Zvuk se zato bira
  // SAMO po javnom kljucu statusa iz odgovora poteza ("gotovo" ili "dorada"), nikad po poenima, budzetu, ceni,
  // minutima ni po bilo kom drugom polju odgovora. Tih neuspeh stize sa kljucem "gotovo", pa dobija zvuk uspeha.
  function zvukIshoda(status) {
    if (!zvukUkljucen) {
      return;
    }
    const zvuk = status === KLJUC_GOTOVO ? TONOVI.gotovo : (status === KLJUC_DORADA ? TONOVI.dorada : null);
    const ctx = zvukPripremi();
    if (!zvuk || !ctx) {
      return;
    }
    try {
      let t = ctx.currentTime;
      zvuk.niz.forEach(function (ton) {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = zvuk.oblik;
        osc.frequency.setValueAtTime(ton[0], t);
        // Envelope: brz uspon i meko gasenje, bez klika na pocetku i kraju tona.
        gain.gain.setValueAtTime(0.0001, t);
        gain.gain.linearRampToValueAtTime(0.15, t + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t + ton[1]);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(t);
        osc.stop(t + ton[1] + 0.02);
        t += ton[1];
      });
    } catch (e) {
      // Zvuk je dodatak: izuzetak iz Web Audio-a ne sme da ubije ostale rukovaoce.
    }
  }

  function nacrtajZvuk() {
    if (!el.zvukDugme) {
      return;
    }
    el.zvukDugme.setAttribute("aria-pressed", zvukUkljucen ? "true" : "false");
    const natpis = T.zvuk && (zvukUkljucen ? T.zvuk.ukljucen : T.zvuk.iskljucen);
    if (typeof natpis === "string") {
      el.zvukDugme.textContent = natpis;
    }
  }

  function pokreniZvuk() {
    // Prekidac je u sablonu skriven; bez Web Audio-a (ili bez dugmeta) ostaje skriven, bez greske.
    if (!el.zvukDugme || !webAudio()) {
      return;
    }
    zvukUkljucen = procitajZvuk();
    nacrtajZvuk();
    el.zvukDugme.hidden = false;
    el.zvukDugme.addEventListener("click", function () {
      zvukUkljucen = !zvukUkljucen;
      upisiZvuk(zvukUkljucen);
      if (zvukUkljucen) {
        zvukPripremi();
      }
      nacrtajZvuk();
    });
  }

  // ---------- Rang lista ----------
  // Ime je tudji unos: ide samo u textContent, nikad u innerHTML, href ni on* atribut.

  function jeRed(red) {
    return jeObjekat(red) &&
      typeof red.ime === "string" && typeof red.datum === "string" &&
      typeof red.ocena === "string" && ima(T.ocene, red.ocena) &&
      typeof red.poeni === "number" && isFinite(red.poeni) &&
      (red.stara_pravila === undefined || typeof red.stara_pravila === "boolean") &&
      (red.red === undefined || typeof red.red === "string");
  }

  // Proverava oblik ranga sa servera; vraca ocisceni objekat ili null ako oblik nije tacan.
  function procitajRang(x) {
    if (!jeObjekat(x) || !Array.isArray(x.lista) || !x.lista.every(jeRed)) {
      return null;
    }
    const moj = Number.isInteger(x.moj) && x.moj >= 0 && x.moj < x.lista.length ? x.moj : null;
    return { lista: x.lista, sacuvano: x.sacuvano === true, moj: moj };
  }

  function jeSacuvano() {
    return sacuvanoOvde || (rang !== null && rang.sacuvano);
  }

  // R4: pitanje pri novoj igri usred partije i na zavrsnom ekranu dok rezultat nije sacuvan.
  function trebaPotvrda() {
    if (!trenutno) {
      return false;
    }
    return trenutno.faza === "igra" || !jeSacuvano();
  }

  // Crta jednu rang listu u zadate elemente (cilj); isti red iz <template> za obe liste.
  // Vraca true ako bar jedan prikazan red nosi oznaku ranijih pravila. Cilj bez elementa se preskace.
  function nacrtajListu(r, cilj) {
    if (!cilj.kontejner || !cilj.redovi || !cilj.tabela || !cilj.prazno || !el.sablonRangRed) {
      return false;
    }
    cilj.redovi.replaceChildren();
    const nijeProcitana = mesto(cilj.kontejner, "nije-procitana");
    if (nijeProcitana) {
      nijeProcitana.hidden = r !== null;
    }
    cilj.prazno.hidden = r === null || r.lista.length > 0;
    cilj.tabela.hidden = r === null || r.lista.length === 0;
    nacrtajPrijavu(r, cilj.kontejner);
    if (r === null) {
      return false;
    }
    let imaStarih = false;
    r.lista.forEach(function (podaci, i) {
      const red = el.sablonRangRed.content.firstElementChild.cloneNode(true);
      mesto(red, "mesto").textContent = String(i + 1);
      mesto(red, "ime").textContent = podaci.ime;
      mesto(red, "poeni").textContent = String(podaci.poeni);
      mesto(red, "ocena").textContent = prevod("ocene", podaci.ocena);
      const staro = podaci.stara_pravila === true;
      mesto(red, "pravila").hidden = !staro;
      imaStarih = imaStarih || staro;
      mesto(red, "datum").textContent = podaci.datum;
      if (i === r.moj) {
        red.classList.add("rang-moj");
        red.setAttribute("aria-current", "true");
        mesto(red, "moj").hidden = false;
      }
      cilj.redovi.appendChild(red);
    });
    return imaStarih;
  }

  // Lista ove strane (glavna na pocetnoj, lista dana na dnevnoj): cuva stanje cuvanja rezultata.
  function nacrtajRang(r) {
    rang = r;
    const imaStarih = nacrtajListu(r, {
      kontejner: el.rang, tabela: el.rangTabela, redovi: el.rangRedovi, prazno: el.rangPrazno,
    });
    if (el.rangLegenda) {
      el.rangLegenda.hidden = !imaStarih;
    }
  }

  // Lista dana na pocetnoj strani: samo citanje (json_script "rang-dana"), bez stanja i bez forme.
  function pokreniRangDana() {
    if (!el.rangDana || !el.rangDanaPodaci) {
      return;
    }
    let podaci = null;
    try {
      podaci = JSON.parse(el.rangDanaPodaci.textContent);
    } catch (e) {
      podaci = null;
    }
    nacrtajListu(procitajRang(podaci), {
      kontejner: el.rangDana, tabela: el.rangDanaTabela, redovi: el.rangDanaRedovi, prazno: el.rangDanaPrazno,
    });
  }

  function imeIzPolja() {
    return el.rangIme.value.normalize("NFC").trim();
  }

  function nacrtajRangDugme() {
    if (el.rangSacuvaj && el.rangIme) {
      el.rangSacuvaj.disabled = uCuvanju || imeIzPolja() === "";
    }
  }

  function nacrtajRangFormu() {
    if (el.rangForma) {
      el.rangForma.hidden = jeSacuvano() || formaZatvorena;
    }
  }

  // Greska polja (polje === true) dobija .is-invalid; ostale greske samo tekst ispod polja.
  function rangGreska(tekst, polje) {
    if (!el.rangGreska || !el.rangIme) {
      return;
    }
    el.rangIme.classList.toggle("is-invalid", polje === true);
    if (polje === true) {
      el.rangIme.setAttribute("aria-invalid", "true");
    } else {
      el.rangIme.removeAttribute("aria-invalid");
    }
    el.rangGreska.textContent = tekst;
    el.rangGreska.hidden = !tekst;
  }

  // Poruka ispod forme: isti izgled za rang listu i deljenje.
  function porukaU(element, tekst, vrsta) {
    if (!element) {
      return;
    }
    if (!tekst) {
      element.hidden = true;
      element.textContent = "";
      return;
    }
    element.classList.toggle("rang-poruka-ok", vrsta === "ok");
    element.classList.toggle("rang-poruka-info", vrsta !== "ok");
    element.textContent = tekst;
    element.hidden = false;
  }

  function rangPoruka(tekst, vrsta) {
    porukaU(el.rangPoruka, tekst, vrsta);
  }

  function rangPorukaSacuvano() {
    rangPoruka(rang !== null && rang.moj === null ? poruke("rangVanListe") : poruke("rangSacuvano"), "ok");
  }

  function obradiCuvanje(status, telo) {
    const kod = jeObjekat(telo) ? telo.greska : null;
    if (status === 200 && jeObjekat(telo) && jeObjekat(telo.rang)) {
      sacuvanoOvde = true;
      nacrtajRang(procitajRang(telo.rang));
      rangGreska("", false);
      nacrtajRangFormu();
      rangPorukaSacuvano();
      // Dugme nestaje sa formom, pa fokus ide na poruku; bez skrolovanja.
      if (el.rangPoruka) {
        el.rangPoruka.focus({ preventScroll: true });
      }
    } else if (status === 400 && (kod === "neispravno_ime" || kod === "nepodobno_ime")) {
      rangGreska(kod === "neispravno_ime" ? poruke("neispravnoIme") : poruke("nepodobnoIme"), true);
      el.rangIme.focus({ preventScroll: true });
    } else if (status === 409 && (kod === "vec_sacuvano" || kod === "igra_nije_zavrsena" || kod === "nema_igre")) {
      const iz = jeObjekat(telo) ? procitajRang(telo.rang) : null;
      if (iz !== null) {
        nacrtajRang(iz);
      }
      if (kod === "vec_sacuvano") {
        sacuvanoOvde = true;
      }
      formaZatvorena = true;
      rangGreska("", false);
      nacrtajRangFormu();
      rangPoruka(
        kod === "vec_sacuvano" ? poruke("vecSacuvano") : kod === "igra_nije_zavrsena" ? poruke("nijeZavrsena") : poruke("nemaIgre"),
        "info"
      );
      if (el.rangPoruka) {
        el.rangPoruka.focus({ preventScroll: true });
      }
    } else if (status === 400) {
      rangGreska(poruke("neispravno"), false);
    } else {
      rangGreska(poruke("server"), false);
    }
  }

  async function sacuvaj(dogadjaj) {
    dogadjaj.preventDefault();
    if (uCuvanju || !el.rangIme || !el.rangForma) {
      return;
    }
    const ime = imeIzPolja();
    if (ime === "") {
      nacrtajRangDugme();
      return;
    }
    uCuvanju = true;
    nacrtajRangDugme();
    rangGreska("", false);
    try {
      const odgovor = await fetch(el.rangForma.dataset.urlSacuvaj, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": procitajKolacic("csrftoken"),
        },
        body: JSON.stringify({ ime: ime }),
      });
      obradiCuvanje(odgovor.status, await procitajOdgovor(odgovor));
    } catch (e) {
      rangGreska(poruke("server"), false);
    } finally {
      uCuvanju = false;
      nacrtajRangDugme();
    }
  }

  function pokreniRang() {
    let podaci = null;
    try {
      podaci = JSON.parse(el.rangPodaci.textContent);
    } catch (e) {
      podaci = null;
    }
    nacrtajRang(procitajRang(podaci));
    nacrtajRangFormu();
    if (el.rangForma && el.rangIme && el.rangSacuvaj) {
      el.rangForma.addEventListener("submit", sacuvaj);
      el.rangIme.addEventListener("input", nacrtajRangDugme);
      nacrtajRangDugme();
      if (jeSacuvano()) {
        rangPorukaSacuvano();
      }
    }
  }

  // ---------- Prijava neprikladnog imena ----------
  // Blok ispod svake liste (sablon _prijava.html): izbor reda, pa slanje. Ime je tudji unos i ide samo u textContent
  // opcije. Oznaka reda stize sa servera uz red liste i vraca se serveru netaknuta; skripta je ne tumaci.

  // Delovi bloka u jednom odeljku liste, ili null ako odeljak nema blok (ili mu nesto nedostaje).
  function deloviPrijave(kontejner) {
    const blok = kontejner ? mesto(kontejner, "prijava") : null;
    if (!blok) {
      return null;
    }
    const d = {
      blok: blok,
      forma: mesto(blok, "prijava-forma"),
      izbor: mesto(blok, "prijava-izbor"),
      dugme: mesto(blok, "prijava-dugme"),
      poruka: mesto(blok, "prijava-poruka"),
    };
    return d.forma && d.izbor && d.dugme && d.poruka ? d : null;
  }

  function nacrtajPrijavaDugme(d) {
    const opcija = d.izbor.options[d.izbor.selectedIndex];
    d.dugme.disabled = uPrijavi || !opcija || opcija.disabled;
  }

  // Red prijavljen sa ove strane ostaje u izboru, ali iskljucen; bira se prvi koji jos nije prijavljen.
  function oznaciPrijavljene(d) {
    let slobodna = null;
    for (const opcija of d.izbor.options) {
      opcija.disabled = prijavljeniRedovi.has(opcija.value);
      if (slobodna === null && !opcija.disabled) {
        slobodna = opcija;
      }
    }
    const izabrana = d.izbor.options[d.izbor.selectedIndex];
    if (slobodna !== null && (!izabrana || izabrana.disabled)) {
      d.izbor.value = slobodna.value;
    }
    nacrtajPrijavaDugme(d);
  }

  // Puni izbor redovima liste; lista bez redova (ili neprocitana) skriva ceo blok.
  function nacrtajPrijavu(r, kontejner) {
    const d = deloviPrijave(kontejner);
    if (!d) {
      return;
    }
    d.izbor.replaceChildren();
    const redovi = r === null ? [] : r.lista;
    redovi.forEach(function (podaci, i) {
      if (typeof podaci.red !== "string" || podaci.red === "") {
        return;
      }
      const opcija = document.createElement("option");
      opcija.value = podaci.red;
      // U+2068 ... U+2069 odvajaju smer imena: ime zdesna nalevo ne pomera redni broj (u tabeli to radi <bdi>).
      opcija.textContent = String(i + 1) + ". ⁨" + podaci.ime + "⁩";
      d.izbor.appendChild(opcija);
    });
    d.blok.hidden = d.izbor.options.length === 0;
    oznaciPrijavljene(d);
  }

  function obradiPrijavu(status, telo, d, oznaka) {
    const kod = jeObjekat(telo) ? telo.greska : null;
    if (status === 200 && jeObjekat(telo) && telo.primljeno === true) {
      prijavljeniRedovi.add(oznaka);
      oznaciPrijavljene(d);
      porukaU(d.poruka, poruke("prijavaPrimljena"), "ok");
    } else if (status === 409 && kod === "nije_na_listi") {
      porukaU(d.poruka, poruke("prijavaNijeNaListi"), "info");
    } else if (status === 409 && kod === "nema_igre") {
      porukaU(d.poruka, poruke("nemaIgre"), "info");
    } else if (status === 400) {
      porukaU(d.poruka, poruke("neispravno"), "info");
    } else {
      porukaU(d.poruka, poruke("server"), "info");
    }
  }

  async function prijavi(dogadjaj, d) {
    dogadjaj.preventDefault();
    const opcija = d.izbor.options[d.izbor.selectedIndex];
    if (uPrijavi || !opcija || opcija.disabled) {
      return;
    }
    const oznaka = opcija.value;
    uPrijavi = true;
    nacrtajPrijavaDugme(d);
    porukaU(d.poruka, "");
    try {
      const odgovor = await fetch(d.forma.dataset.urlPrijavi, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": procitajKolacic("csrftoken"),
        },
        body: JSON.stringify({ red: oznaka }),
      });
      obradiPrijavu(odgovor.status, await procitajOdgovor(odgovor), d, oznaka);
    } catch (e) {
      porukaU(d.poruka, poruke("server"), "info");
    } finally {
      uPrijavi = false;
      nacrtajPrijavaDugme(d);
    }
  }

  function pokreniPrijavu(kontejner) {
    const d = deloviPrijave(kontejner);
    if (!d) {
      return;
    }
    d.forma.addEventListener("submit", function (dogadjaj) {
      prijavi(dogadjaj, d);
    });
    d.izbor.addEventListener("change", function () {
      nacrtajPrijavaDugme(d);
    });
  }

  // ---------- Deljenje rezultata ----------
  // Link stize iz odgovora servera i ide samo u value polja i u navigator.share; nikad u innerHTML ni href.

  function deliPoruka(tekst, vrsta) {
    porukaU(el.deliPoruka, tekst, vrsta);
  }

  function nacrtajDeliDugme() {
    if (el.deliDugme) {
      el.deliDugme.disabled = uDeljenju;
    }
  }

  function pokaziLink(url, istice) {
    el.deliLink.value = url;
    el.deliRok.textContent = obrazac("rok", { datum: istice });
    el.deliBlok.hidden = false;
    // Dugme za slanje postoji samo tamo gde pregledac zna da deli.
    el.deliPosalji.hidden = typeof navigator.share !== "function";
  }

  function obradiDeljenje(status, telo) {
    const kod = jeObjekat(telo) ? telo.greska : null;
    if (status === 200 && jeObjekat(telo) && typeof telo.url === "string" && /^https?:\/\//.test(telo.url) && typeof telo.istice === "string") {
      pokaziLink(telo.url, telo.istice);
      deliPoruka("");
    } else if (status === 409 && kod === "deljenje_isteklo") {
      deliPoruka(poruke("deljenjeIsteklo"), "info");
    } else if (status === 409 && kod === "igra_nije_zavrsena") {
      deliPoruka(poruke("nijeZavrsena"), "info");
    } else if (status === 409 && kod === "nema_igre") {
      deliPoruka(poruke("nemaIgre"), "info");
    } else {
      deliPoruka(poruke("server"), "info");
    }
  }

  async function deli() {
    if (uDeljenju) {
      return;
    }
    uDeljenju = true;
    nacrtajDeliDugme();
    deliPoruka("");
    try {
      const odgovor = await fetch(el.deli.dataset.urlPodeli, {
        method: "POST",
        headers: { "X-CSRFToken": procitajKolacic("csrftoken") },
      });
      obradiDeljenje(odgovor.status, await procitajOdgovor(odgovor));
    } catch (e) {
      deliPoruka(poruke("server"), "info");
    } finally {
      uDeljenju = false;
      nacrtajDeliDugme();
    }
  }

  // Rezerva: polje sa linkom je izabrano, pa se kopira rucno (bez execCommand: zastarelo).
  function oznaciLink() {
    el.deliLink.focus();
    el.deliLink.select();
    el.deliLink.setSelectionRange(0, el.deliLink.value.length);
    deliPoruka(poruke("kopiranjeRezerva"), "info");
  }

  async function kopiraj() {
    const url = el.deliLink.value;
    if (url === "") {
      return;
    }
    if (window.isSecureContext && navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      try {
        await navigator.clipboard.writeText(url);
        deliPoruka(poruke("kopirano"), "ok");
        return;
      } catch (e) {
        // odbijena dozvola ili nedostupan clipboard: rezerva ispod
      }
    }
    oznaciLink();
  }

  async function posaljiLink() {
    const url = el.deliLink.value;
    if (uSlanju || url === "") {
      return;
    }
    if (typeof navigator.share !== "function") {
      oznaciLink();
      return;
    }
    uSlanju = true;
    try {
      await navigator.share({ title: prevod("deljenje", "naslov"), text: prevod("deljenje", "tekst"), url: url });
    } catch (e) {
      if (!e || e.name !== "AbortError") { // AbortError: igrac je odustao, nije greska
        oznaciLink();
      }
    } finally {
      uSlanju = false;
    }
  }

  function pokreniDeljenje() {
    if (!el.deli || !el.deliDugme || !el.deliBlok || !el.deliLink || !el.deliRok || !el.deliKopiraj || !el.deliPosalji) {
      return;
    }
    el.deliDugme.addEventListener("click", deli);
    el.deliKopiraj.addEventListener("click", kopiraj);
    el.deliPosalji.addEventListener("click", posaljiLink);
  }

  // ---------- Deljena strana (samo citanje) ----------

  function jeZavrsni(z) {
    return jeObjekat(z) &&
      typeof z.poeni === "number" && isFinite(z.poeni) && typeof z.ocena === "string" && ima(T.ocene, z.ocena) &&
      typeof z.ukupna_cena === "number" && typeof z.ukupni_minuti === "number" &&
      Array.isArray(z.tihe_greske) && Array.isArray(z.lekcije) &&
      z.tihe_greske.every(function (t) {
        return jeObjekat(t) && typeof t.zadatak === "string" && ima(T.zadaci, t.zadatak) &&
          typeof t.dodatak_cena === "number" && typeof t.dodatak_minuti === "number";
      }) &&
      z.lekcije.every(function (l) {
        return jeObjekat(l) && typeof l.oznaka === "string" && ima(T.lekcije, l.oznaka);
      });
  }

  function pokreniDeljeno() {
    let d = null;
    try {
      d = JSON.parse(el.deljeniRezultat.textContent);
    } catch (e) {
      d = null;
    }
    if (!jeObjekat(d) || !jeZavrsni(d.zavrsni) || typeof d.datum !== "string") {
      poruka(poruke("nijeProcitano"), "greska");
      return;
    }
    nacrtajZavrsni(d.zavrsni);
    // Ime je tudji unos: samo textContent. Bez imena (partija nije sacuvana) red ostaje sakriven.
    if (el.deljenoImeRed && el.deljenoIme) {
      const imaIme = typeof d.ime === "string" && d.ime !== "";
      if (imaIme) {
        el.deljenoIme.textContent = d.ime;
      }
      el.deljenoImeRed.hidden = !imaIme;
    }
    if (el.deljenoDatum) {
      el.deljenoDatum.textContent = d.datum;
    }
    if (el.deljeniPodaci) {
      el.deljeniPodaci.hidden = false;
    }
  }

  function pokreni() {
    // Bez mape tekstova skripta ne zna sta da ispise: prikazuje se samo skriveni prevedeni tekst greske.
    T = procitajTekstove();
    if (T === null) {
      tekstoviNisuProcitani();
      return;
    }

    // Deljena strana nema kontrole igre, rang listu ni dugme za novu igru: grana pre svega ostalog.
    if (el.deljeniRezultat) {
      pokreniDeljeno();
      return;
    }
    if (!el.stanje || !el.kontrole || !el.potvrdi) {
      return;
    }

    // Dnevna strana nema formu "Нова игра" (partija dana se igra jednom), pa je ovde nema.
    if (el.nova) {
      el.nova.addEventListener("submit", function (dogadjaj) {
        if (trebaPotvrda() && !window.confirm(T.pitanjeNova)) {
          dogadjaj.preventDefault();
        }
      });
    }

    pokreniZvuk();
    pokreniRang();
    pokreniRangDana();
    pokreniPrijavu(el.rang);
    pokreniPrijavu(el.rangDana);
    pokreniDeljenje();

    let pocetno = null;
    try {
      pocetno = JSON.parse(el.stanje.textContent);
    } catch (e) {
      pocetno = null;
    }
    if (!jeObjekat(pocetno)) {
      poruka(poruke("stanje"), "greska");
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
