# Auth and Data Architecture Tasks

## Goal

Build dataset-independent authentication, user roles, course management,
enrollment, authorization, and persistent learning-data infrastructure.

## Rules

- Work on branch `auth-and-data-model`.
- Do not push directly to `main`.
- Do not modify the AI model or dataset pipeline.
- Do not redesign the UI.
- Mark completed tasks with `[x]`.

Nemoj trenutno raditi na postojećim question templateovima, matematičkim zadacima, hintovima, Adaptive Engine pravilima ili novom modelu. Novi dataset može imati potpuno drugačiji sadržaj i taksonomiju, pa ne želimo ulagati vrijeme u nešto što ćemo možda zamijeniti.

Glavni cilj naredna dva dana je napraviti generičku backend arhitekturu korisnika, kurseva, studentskih podataka i pristupnih prava koja će biti upotrebljiva bez obzira na dataset i budući model.

Radi na posebnom branchu, npr.:

```text
auth-and-data-model
```

Nemoj pushati direktno na `main`. Praviti odvojene commitove po logičkim cjelinama.

# P0 — autentifikacija i korisničke uloge

- [x] Dodana `accounts` aplikacija.
- [x] Dodan custom Django `User` model.
- [x] Dodane role `student` i `professor`.
- [x] `AUTH_USER_MODEL = "accounts.User"` je postavljen.
- [x] Password hashing je potvrđen.
- [x] `accounts` migracija je kreirana i primijenjena.
- [x] `python manage.py check` prolazi.
- [x] Dodan custom Django User model sa rolama student i professor.
- [x] Registracija kreira samo student korisnike.
- [x] Username, ime, prezime, email i potvrda lozinke se validiraju.
- [x] Passwordi se čuvaju kroz Django hashing.
- [x] Login radi sa usernameom ili emailom i passwordom.
- [x] Pogrešan password se odbija.
- [x] Login koristi Django `authenticate()` i `login()`.
- [x] Logout koristi Django `logout()`.
- [x] Logout briše privremeni learning runtime state.
- [x] Neprijavljen korisnik se preusmjerava na login.
- [x] Stari `select-user` endpoint više ne omogućava passwordless pristup.

## 1. Uvesti pravi Django User model 

Trenutni sistem u `users.json` i izbor postojećeg usernamea treba zamijeniti pravom Django autentifikacijom.

Pošto projekat još nema vlastite Django modele ni važne produkcijske migracije, sada je odgovarajući trenutak za custom user model.

Preporučena struktura:

```python
class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        PROFESSOR = "professor", "Professor"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT,
    )
```

Poželjno je napraviti zasebnu Django aplikaciju `accounts`, umjesto stavljanja svega u `learning`.

U `settings.py` postaviti:

```python
AUTH_USER_MODEL = "accounts.User"
```

Obavezno koristiti Django password hashing. Lozinke se nikada ne smiju čuvati u JSON-u, sessionu, logovima ili kao običan tekst.

Acceptance criteria:

* korisnik se čuva u Django bazi;
* password je hashiran;
* postoje dvije uloge: student i professor;
* `users.json` više nije izvor autentifikacije;
* `request.user` predstavlja prijavljenog korisnika;
* postoje migracije koje prolaze na čistoj bazi.

## 2. Implementirati registraciju studenta

Napraviti backend registraciju sa:

* usernameom;
* imenom;
* prezimenom;
* emailom;
* passwordom;
* potvrdom passworda.

Nova javna registracija uvijek treba praviti:

```text
role = student
```

Korisnik ne smije kroz POST request proizvoljno poslati `role=professor` i tako postati profesor.

Validacija:

* jedinstven username;
* jedinstven email, ako odlučimo da je email obavezan;
* password i potvrda moraju biti isti;
* koristiti Django password validatore;
* prikazati normalne validation errors;
* nakon registracije korisnik se može automatski prijaviti ili preusmjeriti na login.

Nije potrebno dizajnirati stranicu. Dovoljna je minimalna funkcionalna forma koju ćemo kasnije vizuelno urediti.

## 3. Implementirati login i logout

Ukloniti postojeći tok u kojem se korisnik bira s liste bez lozinke.

Login mora tražiti:

* username ili email;
* password.

Potrebno je koristiti Django:

```python
authenticate()
login()
logout()
```

Nakon logouta:

* Django autentifikacijska sesija mora biti završena;
* trenutno pitanje i privremeno practice stanje treba očistiti;
* korisnik se vraća na login;
* browser back ne smije omogućiti pristup zaštićenim podacima bez ponovnog loginovanja.

Acceptance criteria:

* nije moguće pristupiti postojećem accountu bez passworda;
* pogrešan password se odbija;
* ispravan password prijavljuje korisnika;
* logout zaista ukida pristup;
* stari `select-user` endpoint više nije dostupan ili preusmjerava na login.

## 4. Sigurno kreiranje professor accounta

Professor account se ne treba moći dobiti običnom javnom registracijom.

Implementirati jednu od ovih mogućnosti, preporučeno prvu:

1. professor se kreira kroz Django admin;
2. management command `create_professor`;
3. registration code koji se čuva u `.env`.

Najjednostavnije i najsigurnije za projekat je Django admin ili komanda:

```bat
python manage.py create_professor
```

Komanda može tražiti username, email i password bez njihovog ispisivanja u log.

Acceptance criteria:

* obična registracija ne može napraviti profesora;
* professor account se može pouzdano kreirati;
* uloga se čuva u bazi;
* password nije spremljen kao običan tekst.

- [x] Obična javna registracija ne može kreirati profesora.
- [x] Dodana `create_professor` management command.
- [x] Professor se kreira sa `role = "professor"`.
- [x] Username i email duplikati se odbijaju.
- [x] Professor password se postavlja preko `set_password()`.
- [x] Password hashing je ručno potvrđen preko `check_password()`.

# P0 — generički akademski modeli

## 5. Dodati Course/Classroom model

Napraviti generički model koji predstavlja kurs ili grupu kojom profesor upravlja.

Primjer:

```python
class Course(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=30, unique=True)
    professor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="courses_taught",
        limit_choices_to={"role": "professor"},
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

Ne koristiti nazive vezane isključivo za matematiku.

Acceptance criteria:

* jedan profesor može imati više kurseva;
* svaki kurs ima jednog odgovornog profesora;
* student nije moguće postaviti kao profesora kursa;
* kod kursa je jedinstven.

## 6. Dodati Enrollment model

Povezivanje studenta s kursom ne treba staviti direktno u User model jer student kasnije može pripadati različitim kursevima.

Primjer:

```python
class Enrollment(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="enrollments",
        limit_choices_to={"role": "student"},
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["course", "student"],
                name="unique_course_student",
            )
        ]
```

Acceptance criteria:

* student može biti upisan na kurs;
* isti student ne može dvaput biti upisan na isti kurs;
* professor nije moguće upisati kao studenta;
* profesor može dohvatiti samo studente svojih kurseva.

- [x] Dodan generički `Course` model.
- [x] Jedan professor može imati više kurseva.
- [x] Svaki Course ima jednog odgovornog profesora.
- [x] Student ne može biti postavljen kao professor kursa.
- [x] `Course.code` je jedinstven.
- [x] Dodan je jedinstven `enrollment_code`.
- [x] Dodan `Enrollment` model.
- [x] Student može biti upisan na kurs.
- [x] Professor ne može biti upisan kao student.
- [x] Dupli enrollment se odbija preko `unique_course_student`.

## 7. Napraviti način upisa studenta na kurs

Implementirati jednostavan i generički sistem upisa.

Najpraktičnija opcija:

* Course ima jedinstven enrollment code;
* student nakon loginovanja unese kod;
* kreira se Enrollment;
* pogrešan ili neaktivan kod se odbija;
* ponovni unos istog koda ne pravi duplikat.

Alternativno, profesor može dodati studenta preko usernamea ili emaila.

Nije potrebno dizajnirati interfejs. Dovoljni su backend forma, endpoint i minimalna funkcionalna stranica.

- [x] Dodana forma za upis studenta na kurs preko enrollment code-a.
- [x] Samo prijavljen student može poslati enrollment zahtjev.
- [x] Ispravan enrollment code kreira Enrollment.
- [x] Pogrešan enrollment code se odbija.
- [x] Neaktivan kurs se odbija.
- [x] Ponovni upis istim kodom ne stvara duplikat.
- [x] Professor ne može koristiti student enrollment endpoint.

# P0 — generička struktura znanja

## 8. Napraviti generički KnowledgeComponent model

Ne hardkodirati postojeće `S01_ARITH`, `S02_FRAC` i ostale matematičke skillove.

Napraviti generički model:

```python
class KnowledgeComponent(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="knowledge_components",
    )
    external_id = models.CharField(max_length=200)
    name = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["course", "external_id"],
                name="unique_component_per_course",
            )
        ]
```

`external_id` će kasnije omogućiti povezivanje s bilo kojim datasetom. `metadata` može čuvati dataset-specifične informacije bez promjene šeme.

Ne importovati sada postojeće matematičke skillove ako to komplikuje rad. Bitno je napraviti generičku strukturu i testne instance.

- [x] Dodan generički KnowledgeComponent model.
- [x] Komponenta pripada Course modelu.
- [x] `external_id` je unique unutar coursea.
- [x] Podržana je parent/child hijerarhija.
- [x] Parent mora pripadati istom courseu.
- [x] Podržan je fleksibilni metadata JSON.
- [x] Django admin prikazuje komponente.

## 9. Napraviti StudentKnowledgeState model

Potrebna je generička tabela u kojoj će se kasnije čuvati procijenjeno znanje studenta, neovisno o vrsti modela.

Primjer:

```python
class StudentKnowledgeState(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="knowledge_states",
    )
    knowledge_component = models.ForeignKey(
        KnowledgeComponent,
        on_delete=models.CASCADE,
        related_name="student_states",
    )
    mastery = models.FloatField(null=True, blank=True)
    source = models.CharField(max_length=100, default="unknown")
    source_version = models.CharField(max_length=100, blank=True)
    evidence_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "knowledge_component"],
                name="unique_student_component_state",
            )
        ]
```

Ne dodavati logiku budućeg modela. Ovaj model samo čuva rezultat koji može dolaziti iz BKT-a, DKT-a ili drugog sistema.

Validacija:

* `mastery` je `null` ako još nema procjene;
* ako postoji, mora biti između `0` i `1`;
* student mora biti upisan na kurs kojem knowledge component pripada;
* jedno stanje po studentu i knowledge componentu.

- [x] Dodan StudentKnowledgeState model.
- [x] Stanje povezuje Enrollment i KnowledgeComponent.
- [x] mastery_prob je float (0–1).
- [x] last_attempt_at i last_updated_at su ispravno definisani.
- [x] (enrollment, knowledge_component) je unique.
- [x] Validacija: komponenta mora biti iz istog kursa kao i upis.
- [x] Django admin prikazuje stanja.

## 10. Napraviti generički LearningAttempt model

Potrebno je imati bazu interakcija koja nije vezana za trenutni format pitanja.

Primjer polja:

```text
student
course
knowledge_component
external_question_id
question_type
answer
is_correct
score
response_time_ms
hint_count
attempt_number
started_at
submitted_at
metadata
```

`external_question_id` i `metadata` omogućavaju da kasnije koristimo različite datasete.

Ako jedan zadatak može imati više knowledge componenta, koristiti ManyToMany vezu ili posebni `AttemptKnowledgeComponent` model. Ne pretpostavljati da svaki zadatak nužno pripada samo jednom skillu.

Ne praviti sada dataset import niti modelsku predikciju.

Acceptance criteria:

* pokušaj je vezan za stvarnog prijavljenog studenta;
* attempt drugog studenta nije dostupan trenutnom studentu;
* profesor ga vidi samo ako student pripada njegovom kursu;
* podržana su pitanja s jednim ili više knowledge componenta;
* dodatna dataset-specifična polja mogu stati u `metadata`.

## 11. Napraviti LearningSession model

Session ne treba ostati samo nasumični ID u Parquet fajlu.

Predložena polja:

```text
student
course
started_at
ended_at
is_active
goal_component (nullable)
metadata
```

Pravila:

* aktivna sesija pripada prijavljenom studentu;
* student ne može otvoriti ili završiti tuđu sesiju;
* završena sesija se ne mijenja;
* logout može zatvoriti aktivnu sesiju ili je ostaviti jasno označenu;
* session podaci ostaju sačuvani nakon novog loginovanja.

# P0 — autorizacija i privatnost

## 12. Zaštititi sve interne viewove

Sve stranice osim registracije i login stranice moraju zahtijevati autentifikaciju.

Koristiti:

```python
@login_required
```

ili odgovarajuće class-based mixine.

Napraviti role dekoratore ili permission funkcije:

```python
student_required
professor_required
```

Pravila:

* student ne može otvoriti professor endpoint;
* professor ne može koristiti student ID iz URL-a da vidi studenta koji nije na njegovom kursu;
* student ne može promijeniti URL i vidjeti tuđi progress;
* neprijavljen korisnik se preusmjerava na login;
* POST endpointi ostaju CSRF zaštićeni;
* podaci se uvijek filtriraju prema `request.user`, a ne samo prema ID-u iz requesta.

Ovo je posebno važno: nije dovoljno sakriti link. Backend mora odbiti neovlašten zahtjev.

## 13. Implementirati professor podatkovni pregled

Bez dizajniranja UI-ja napraviti backend servis/query funkcije koje profesoru vraćaju:

* njegove kurseve;
* studente po kursu;
* broj pokušaja svakog studenta;
* knowledge components studenta;
* trenutni mastery, ako postoji;
* vrijeme posljednje aktivnosti;
* prosječnu tačnost;
* broj aktivnih/završenih sesija.

Napraviti view koji koristi te queryje i minimalni template ili JSON/debug prikaz. Vizuelno uređenje ćemo raditi kasnije.

Professor smije vidjeti samo podatke studenata koji su upisani na njegove kurseve.

## 14. Implementirati student podatkovni pregled

Backend servis za studenta treba vraćati isključivo:

* njegove kurseve;
* njegove knowledge states;
* njegove pokušaje;
* njegove sesije;
* njegov progress.

Student ID ne treba uzimati iz URL-a ako nije potreban. Koristiti:

```python
request.user
```

Acceptance criteria:

* student nikako ne može dohvatiti podatke drugog studenta;
* čak ni ručnim mijenjanjem URL-a;
* čak ni slanjem modificiranog POST requesta.

# P1 — migracija postojećeg sistema

## 15. Ukloniti stari user-selection sistem

Postojeće funkcije poput:

```text
login_existing
create_and_login
select_user_view
users.json
```

treba postepeno ukloniti ili prestati koristiti.

Potrebno je:

* ukloniti mogućnost listanja svih usernameova;
* ukloniti ulazak u account klikom na username;
* zamijeniti `session["student_id"]` vezom s `request.user`;
* gdje stari kod očekuje `student_id`, koristiti stabilni interni identifikator prijavljenog korisnika;
* privremeno zadržati compatibility helper samo ako je potreban da aplikacija nastavi raditi.

Postojeće demo korisnike nije potrebno migrirati ako nisu stvarni računi. Možemo ih ponovo kreirati kroz seed komandu.

## 16. Prebaciti runtime podatke s JSON/Parquet storagea

Kada osnovni Django modeli prorade, novi korisnici, sesije i pokušaji trebaju se zapisivati u bazu, a ne u:

```text
users.json
events.parquet
session_summaries.parquet
```

Ne moraš odmah brisati stare module. Možeš:

1. napraviti Django repository/service implementaciju;
2. prebaciti nove write operacije na bazu;
3. ostaviti stari Parquet loader samo za eventualni import;
4. dodati management command za import starih demo događaja, ako je jednostavno.

Najvažnije je da ne postoje dva aktivna izvora istine.

Canonical izvor treba postati Django baza.

## 17. Napraviti seed komandu za demo korisnike

Dodati management command:

```bat
python manage.py seed_demo
```

Komanda treba napraviti:

* jednog profesora;
* jedan kurs;
* najmanje dva studenta;
* enrollment oba studenta;
* nekoliko generičkih knowledge componenta;
* nekoliko knowledge state zapisa;
* nekoliko pokušaja.

Koristiti jasno demo podatke, npr.:

```text
professor_demo
student_demo_1
student_demo_2
```

Passwordi se postavljaju kroz `set_password`, nikada direktno.

Komanda treba biti idempotentna: ponovno pokretanje ne pravi duplikate.

# P0/P1 — testovi

## 18. Dodati testove autentifikacije

Testirati:

* registracija pravi student account;
* nije moguće registracijom poslati `role=professor`;
* password je hashiran;
* tačan password radi;
* pogrešan password se odbija;
* logout završava autentifikaciju;
* neprijavljen korisnik ne može otvoriti interne stranice;
* stari select-user endpoint više ne omogućava pristup.

## 19. Dodati testove autorizacije

Kreirati:

* professor A;
* professor B;
* student A na kursu professora A;
* student B na kursu professora B.

Testirati:

* professor A vidi studenta A;
* professor A ne vidi studenta B;
* professor B ne vidi studenta A;
* student A vidi samo vlastite podatke;
* student A ne može dohvatiti student B podatke;
* student ne može otvoriti professor stranice;
* anonimni korisnik ne može dohvatiti ništa interno.

Testirati i direktan pristup URL-ovima, ne samo vidljivost linkova.

## 20. Dodati model validation testove

Testirati:

* student ne može biti course professor;
* professor ne može biti enrollment student;
* dupli enrollment se odbija;
* dupli knowledge state se odbija;
* mastery izvan `[0,1]` se odbija;
* student mora pripadati odgovarajućem kursu;
* course code/enrollment code je jedinstven;
* brisanje coursea korektno rješava povezane podatke.

# Završna provjera

Prije PR-a pokrenuti:

```bat
python manage.py makemigrations
python manage.py migrate
python manage.py check
python manage.py test
python manage.py runserver
```

Ručno provjeriti:

1. registraciju studenta;
2. login s passwordom;
3. pogrešan password;
4. logout;
5. kreiranje professora;
6. kreiranje kursa;
7. upis studenta;
8. professor pristup svojim studentima;
9. zabranu pristupa tuđim studentima;
10. student pristup samo vlastitim podacima.

U Pull Requestu navesti:

* koje modele si dodala;
* koje migracije postoje;
* kako se kreira professor;
* kako se student upisuje na kurs;
* šta je uklonjeno iz starog user sistema;
* da li se novi pokušaji čuvaju u Django bazi;
* rezultate testova;
* šta nije završeno.

Ne raditi:

* novi AI model;
* dataset preprocessing;
* mapiranje konkretnog dataseta;
* popravljanje postojećih matematičkih templateova;
* redizajn UI-ja;
* LLM funkcionalnosti;
* model-specifičnu adaptivnu logiku.
