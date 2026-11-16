# Ovlascenje po id-u: postupak

Ucitava se kada agent pise ili pregleda endpoint koji prima identifikator.

## Postupak (ne gledaj kod "da li deluje sumnjivo", nego nabroji)

1. Nabroji SVE ulaze zahteva: putanja, query string, telo, zaglavlja.
2. Za svaki koji je identifikator objekta: odakle se objekat cita?
3. Da li to citanje prolazi kroz isti helper opsega kao lista tog objekta?
4. Ako ne: nalaz, bez obzira sto "korisnik to ionako ne bi znao".

## Endpointi koji se najcesce zaborave

- Akcije bez sablona (POST koji menja stanje pa preusmerava: odobri, odbij, zatvori).
  Niko ih ne otvara u pregledacu, pa ih niko ne testira rucno.
- Izvoz (CSV, PDF): drugi kod puta, cesto bez filtera.
- Agregati (brojaci, statistike): `count()` bez opsega otkriva tudje podatke kao broj.
- Pretraga i automatsko dopunjavanje (autocomplete).

## Test koji se pise uz svaki takav endpoint

Korisnik iz opsega A trazi objekat iz opsega B → ocekivano 404. Test sa dva
korisnika, ne sa jednim.
