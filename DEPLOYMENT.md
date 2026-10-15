# Deploying Dhruv Online Academy

Everything needed to put this application on Google Cloud Run, in order. Follow the steps
as written; each one checks itself before the next begins.

**Roughly 90 minutes**, plus waiting time for the email domain.

> Doing this without `gcloud`, or handing it to somebody who does not write code?
> [DEPLOYMENT-HINDI.md](DEPLOYMENT-HINDI.md) covers the same ground in Hindi, entirely
> through the Google Cloud Console screens — every step is a form or a button, and it
> explains what each setting is for. The two guides produce the same result.

---

## What you are building

One Cloud Run service. The container holds both halves of the application: the web pages
and the API, answering on the same address.

```
   visitors ──► Cloud Run  (dhruv-app)  ──► MongoDB Atlas
                  │                             (the database)
                  ├── /            the web pages
                  ├── /api/v1/…    the API
                  └── /healthz     "is it alive?"
```

One service rather than two, because the sign-in cookies only travel when the pages and
the API share an address. Splitting them would silently sign people out.

---

## Before you start

You need:

- A **Google Cloud project**, with billing enabled
- A **MongoDB Atlas** account
- A **Resend** account (for sending the one-time codes)
- The `gcloud` command installed, and `gcloud auth login` done

And one decision: **the email address of the first administrator.** That person needs to
be available at the end to collect a code and set their password.

---

## Step 1 — Create the database

In MongoDB Atlas:

1. **Create a cluster.** The free M0 tier is enough to start. Choose region **Mumbai
   (`ap-south-1`)** so it sits beside the application.
2. **Database Access → Add New Database User.** Give it a strong password and the
   *Read and write to any database* role. Write the password down somewhere safe.
3. **Network Access → Add IP Address → Allow access from anywhere (`0.0.0.0/0`).**

   Cloud Run does not have fixed outgoing addresses, so the list cannot name them. The
   database is still protected by its username and password, which is the real lock.
   Tightening this later needs a VPC connector with a static address.
4. **Connect → Drivers** and copy the connection string. It looks like:

   ```
   mongodb+srv://USERNAME:PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```

   Replace `PASSWORD` with the real one. **If the password contains `@`, `/`, `:` or `#`,
   replace those characters with their codes** — `@` becomes `%40`, `/` becomes `%2F`,
   `:` becomes `%3A`, `#` becomes `%23`. A password pasted in raw is the single most
   common reason the first deploy cannot connect.

---

## Step 2 — Start the email domain (do this now, it involves waiting)

Nobody can sign in until email works, including the first administrator. Start it early.

In Resend:

1. **Domains → Add Domain** → `dhruvonlineacademy.com`
2. Resend shows DNS records to add. In Namecheap: **Domain List → Manage → Advanced DNS**,
   and add them exactly as shown.
3. **API Keys → Create** and copy the key.

### Two things to be careful about

**Do not touch the MX records.** They control *incoming* mail to the domain, and someone
is receiving mail on it today. Sending email from the application does not need them
changed. If Resend asks for an MX record on a *subdomain* such as `bounces.…`, that is
different and safe — read the host column carefully.

**There must be exactly one SPF record.** If the domain already has one, edit it rather
than adding a second. Two SPF records is a configuration error, and the symptom is your
password emails quietly going to spam.

```
before:  v=spf1 include:spf.efwd.registrar-servers.com ~all
after:   v=spf1 include:spf.efwd.registrar-servers.com include:_spf.resend.com ~all
```

Verification takes anywhere from minutes to a few hours. Carry on with the next steps
while you wait.

> **Until the domain is verified**, Resend will only deliver to the address the account
> was registered with. That is enough to set up the first administrator; it is not enough
> to invite anybody else.

---

## Step 3 — Generate the secrets

Three values the application needs, which must never be written into the code or sent
over chat.

**The signing keys** — run these two commands and keep the output:

```bash
openssl ecparam -genkey -name prime256v1 -noout -out jwt.pem
openssl ec -in jwt.pem -pubout
```

The first prints nothing and writes `jwt.pem` — that file is the **private key**. The
second prints the **public key**.

**The one-time-code pepper:**

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Delete `jwt.pem` from your computer once it is in Secret Manager (step 4).** If any of
these three ever appears in a commit, a chat message or a screenshot, generate new ones —
removing them is not enough, because they have already been seen.

---

## Step 4 — Put the secrets in Google Cloud

Set your project and region once:

```bash
gcloud config set project YOUR_PROJECT_ID
gcloud config set run/region asia-south1
```

Turn on the services this uses:

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com
```

Create somewhere to keep the built images:

```bash
gcloud artifacts repositories create dhruv \
  --repository-format=docker --location=asia-south1
```

Now store each secret. Repeat this for every value, replacing the name each time:

```bash
printf '%s' 'THE VALUE' | gcloud secrets create MONGODB_URL --data-file=-
```

The five secrets:

| Name | Value |
|---|---|
| `MONGODB_URL` | the Atlas connection string from step 1 |
| `JWT_PRIVATE_KEY` | the contents of `jwt.pem` |
| `JWT_PUBLIC_KEY` | the public key printed in step 3 |
| `OTP_PEPPER` | the random string from step 3 |
| `RESEND_API_KEY` | the key from step 2 |

For the two keys, which run over several lines, read them from the file instead:

```bash
gcloud secrets create JWT_PRIVATE_KEY --data-file=jwt.pem
```

Then **delete `jwt.pem`**.

---

## Step 5 — Build and deploy

Build the image first, from the project folder. Thirty minutes of headroom, because the
image compiles the React app before it installs Python:

```bash
gcloud builds submit --timeout=1800s \
  --tag=asia-south1-docker.pkg.dev/YOUR_PROJECT_ID/dhruv/dhruv-app:first .
```

Five to ten minutes. Then create the service, **with the secrets attached in the same
command**:

```bash
gcloud run deploy dhruv-app \
  --image=asia-south1-docker.pkg.dev/YOUR_PROJECT_ID/dhruv/dhruv-app:first \
  --region=asia-south1 --platform=managed --allow-unauthenticated \
  --port=8000 --no-cpu-throttling --max-instances=4 --min-instances=0 \
  --memory=1Gi --cpu=1 --timeout=300 \
  --set-env-vars=ENVIRONMENT=production,MONGODB_DB_NAME=dhruv,FRONTEND_URL=https://dhruvonlineacademy.com,JWT_KEY_ID=k1,SEED_SUPERADMIN_EMAIL=admin@example.com \
  --set-env-vars='EMAIL_FROM=Dhruv Online Academy <noreply@dhruvonlineacademy.com>' \
  --set-secrets=MONGODB_URL=MONGODB_URL:latest,JWT_PRIVATE_KEY=JWT_PRIVATE_KEY:latest,JWT_PUBLIC_KEY=JWT_PUBLIC_KEY:latest,OTP_PEPPER=OTP_PEPPER:latest,RESEND_API_KEY=RESEND_API_KEY:latest
```

**Change `SEED_SUPERADMIN_EMAIL` to the real first administrator's address** before
running this. Forget it and the deploy will succeed, everything will look healthy, and
there will be no way to sign in.

The secrets go on in that same command rather than afterwards, because the application
refuses to start without the signing keys — it signs and verifies a throwaway token at
boot so that a broken key fails the deploy instead of surfacing as a 500 on somebody's
first login. Deploy without them and the revision never turns healthy.

`cloudbuild.yaml` is for *later* deploys, once this one has worked — it only replaces the
image, and Cloud Run keeps the settings and secrets you attached here.

### Check it

```bash
gcloud run services describe dhruv-app --format='value(status.url)'
```

Open that address with `/healthz` on the end. You should see:

```json
{"status":"ok","environment":"production","version":"0.1.0"}
```

Then `/healthz/db`, which is the one that matters — it actually talks to Atlas:

```json
{"status":"ok","database":"reachable"}
```

`/healthz` deliberately does not touch the database, so that a slow query cannot restart
the service in a loop. Which means it can answer `ok` while the database is unreachable.
Always check both.

If either fails, read the logs:

```bash
gcloud run services logs read dhruv-app --limit=50
```

---

## Step 6 — Set up the database contents

The database is empty. One command fills it with the roles, the permissions and the first
administrator's account.

Create the task runner once — it uses the same image as the application:

```bash
IMAGE=$(gcloud run services describe dhruv-app --format='value(spec.template.spec.containers[0].image)')

gcloud run jobs create dhruv-admin \
  --image="$IMAGE" \
  --region=asia-south1 \
  --command=python \
  --args=-m,app.cli,list-super-admins \
  --set-env-vars=ENVIRONMENT=production,MONGODB_DB_NAME=dhruv,SEED_SUPERADMIN_EMAIL=admin@example.com \
  --set-secrets=MONGODB_URL=MONGODB_URL:latest,JWT_PRIVATE_KEY=JWT_PRIVATE_KEY:latest,JWT_PUBLIC_KEY=JWT_PUBLIC_KEY:latest,OTP_PEPPER=OTP_PEPPER:latest
```

Then run the setup:

```bash
gcloud run jobs execute dhruv-admin --region=asia-south1 --wait \
  --args=-m,app.cli,seed
```

It prints `Seed complete`. **It is safe to run again** — it adds what is missing and
deletes nothing.

> Run this as a job rather than letting the application do it at start-up, so it happens
> once, deliberately, with a visible result. Several containers starting at the same
> moment would otherwise all try to create the same records, and all but one would crash
> on a unique index. For the same reason, **do not set `RUN_MIGRATIONS_ON_START` on Cloud
> Run** — that switch exists for hosts that have no way to run a one-off command.

> If your `gcloud` is too old to accept `--args` on `execute`, set the arguments on the
> job first and then run it with no arguments:
>
> ```bash
> gcloud run jobs update dhruv-admin --region=asia-south1 --args=-m,app.cli,seed
> gcloud run jobs execute dhruv-admin --region=asia-south1 --wait
> ```

---

## Step 7 — The first administrator signs in

This is the part people get wrong, so it is worth reading before doing.

**The application never creates a password.** A password made by a script ends up in a
log, a terminal history, or a screenshot. So the first administrator's account is created
*without* one, and they set it themselves — which also proves the email address is really
theirs.

Check the account exists:

```bash
gcloud run jobs execute dhruv-admin --region=asia-south1 --wait \
  --args=-m,app.cli,list-super-admins
```

You should see their address, marked `invited`. Then:

1. The administrator opens the site and clicks **Forgot password**
2. They enter their email address
3. A six-digit code arrives in their inbox
4. They enter it and choose a password
5. They are in

Their status changes from `invited` to `active`.

**If the code does not arrive:** email is not working yet. Check the Resend dashboard, and
remember that before the domain is verified Resend only delivers to the address the Resend
account itself was registered with.

### Adding another administrator later

Deliberately not possible from inside the application. Nobody — not even a Super Admin —
can hand out their own level of access through the web pages, because who controls the
platform should not be decided by a browser session that could be stolen.

It is this command:

```bash
# Somebody who already has an account
gcloud run jobs execute dhruv-admin --region=asia-south1 --wait \
  --args=-m,app.cli,grant-super-admin,someone@example.com

# A brand-new address
gcloud run jobs execute dhruv-admin --region=asia-south1 --wait \
  --args=-m,app.cli,grant-super-admin,someone@example.com,--create

# Take it away again
gcloud run jobs execute dhruv-admin --region=asia-south1 --wait \
  --args=-m,app.cli,revoke-super-admin,someone@example.com

# Who has it
gcloud run jobs execute dhruv-admin --region=asia-south1 --wait \
  --args=-m,app.cli,list-super-admins
```

Every one of these is written to the activity log. Removing the role also signs that
person out everywhere, immediately. And the command refuses to remove the last
administrator who can actually sign in — so the platform can never be left with nobody in
charge.

---

## Step 8 — Point the domain at it

Only once everything above works on the Cloud Run address.

```bash
gcloud beta run domain-mappings create \
  --service=dhruv-app --domain=dhruvonlineacademy.com --region=asia-south1
```

Google gives you DNS records. Add them in Namecheap, under Advanced DNS.

**Leave the MX records alone.** Again: they are the domain's incoming mail, and nothing
about this deployment needs them changed.

Certificates take fifteen minutes to an hour to issue. Until then the address will show a
security warning, which is expected.

---

## Step 9 — Check before telling anyone

On the real address:

- [ ] `https://dhruvonlineacademy.com/healthz` answers, with no browser warning
- [ ] The administrator signs in
- [ ] Create a test institute; confirm its administrator sees only that institute
- [ ] Invite someone and complete setup from the emailed code
- [ ] Forgot password works end to end, to a real inbox
- [ ] Open it on a phone
- [ ] **Send an email to an address at the domain from outside, and confirm it still
      arrives** — this is the one people forget

---

## Later deploys

Once Cloud Build is connected to the repository (**Cloud Build → Triggers → Create**,
pointing at `cloudbuild.yaml`), every push rebuilds and deploys by itself.

Nothing needs re-running: the secrets and settings stay attached to the service. Run the
seed again only after a release that adds new roles or permissions — and it is safe either
way.

**To undo a bad deploy:**

```bash
gcloud run revisions list --service=dhruv-app --region=asia-south1
gcloud run services update-traffic dhruv-app --region=asia-south1 --to-revisions=REVISION_NAME=100
```

Traffic moves back in seconds.

---

## When something is wrong

| What you see | Usually |
|---|---|
| Container fails to start | `MONGODB_URL` wrong, or the password not escaped (step 1) |
| Starts, but every page errors | Atlas Network Access does not allow the connection |
| Nobody can sign in | `SEED_SUPERADMIN_EMAIL` was not set, or the seed has not run |
| Codes never arrive | No `RESEND_API_KEY`, or the domain is not verified yet |
| Emails go to spam | Two SPF records, or DKIM not added |
| Slow first request after a quiet period | The service scaled to zero. Set `--min-instances=1` to stop it |

Logs:

```bash
gcloud run services logs read dhruv-app --region=asia-south1 --limit=100
```

---

## Two numbers that must stay in step

If you ever raise how many containers may run at once, raise the database connection limit
with it — or lower it. The rule:

```
max-instances  ×  MONGODB_MAX_POOL_SIZE  ≤  0.8 × the Atlas cluster's connection limit
```

The defaults are 4 instances × 20 connections = 80, comfortably inside a free cluster's
500. Going past that without adjusting it produces failures that only appear under the
traffic you were hoping for.

---

## A note on `render.yaml`

There is a `render.yaml` in the project. It deploys the same image, the same way, to
Render instead of Google Cloud — a cheaper fallback if Cloud Run is ever not wanted. It
uses the same MongoDB Atlas database and the same secrets.

**Ignore it when following this document.** The two are alternatives, not steps; running
both would give you two copies of the site sharing one database.
