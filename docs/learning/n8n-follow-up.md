# n8n follow-up

This explains the first n8n workflow in Sentinel. Read it after the browser-check section of the [technical walkthrough](milestone-1-technical-walkthrough.md). The workflow does not open a browser and it does not call an AI model.

## The idea

A workflow is a list of steps that a separate program runs. n8n is that program. Sentinel keeps the websites and the check rows. n8n asks Sentinel for those rows and, when the newest check failed, writes a short message you can read in the n8n execution.

The message is a draft. Nothing is emailed and nothing is posted to chat. The draft is the seam where a later Slack or email node will go. Putting the destination in n8n means Sentinel does not grow a mail client of its own.

n8n calls Sentinel. Sentinel does not call n8n. The arrow matters. The API stays the place that knows how to store a check. n8n stays the place that decides what to do after a result exists. A later feature can add a schedule, a chat message, or an AI explanation without moving the browser code into n8n.

## Why it is a separate process

The API and the website run on Windows so reload stays ordinary. PostgreSQL and n8n run in Docker. n8n has its own database, a SQLite file in the Compose volume `sentinel_n8n_data`. Docker stores that volume as `sentinel_sentinel_n8n_data`. The file holds the editor account and the imported workflow. It is not the `websites` table and it is not `website_checks`.

The two databases are separate on purpose. Sentinel's password is not given to the n8n container. n8n also blocks workflows from reading the container's environment. The API address is therefore written in the workflow, in the node named **API address**, where you can see it. The same address is copied into `.env.example` as `SENTINEL_API_URL` so there is one documented value. n8n does not load that variable.

`http://host.docker.internal:8000` means "the Docker host, port 8000". Inside the container, `localhost` is n8n itself, not the API. Compose adds the name `host.docker.internal` because Docker Engine on Linux does not provide it by itself. On this computer that host is Ubuntu, where Docker is running. It is not the Windows loopback where you usually start Uvicorn.

## What each node does

The file is `n8n/workflows/failed-check-follow-up.json`. The workflow is inactive. Inactive means a trigger that listens in the background does not run. This workflow has no such trigger. You run it by hand.

| Node | What it does |
| --- | --- |
| Run follow-up | Manual trigger. The run starts only when you execute the workflow. |
| API address | Sets `apiBase` to `http://host.docker.internal:8000`. |
| List websites | `GET /api/websites`. One item per website. |
| Latest check | `GET /api/websites/{id}/checks?limit=1`. The API returns the newest check. |
| Check failed | Continues only when `outcome` is `failed`. A website with no checks, or a successful check, stops here. |
| Notification draft | Builds `website_name`, `base_url`, `outcome`, `http_status`, `error_message`, and `checked_at`. |

Both HTTP nodes are `GET`. The workflow does not send `authorized`, and it does not call `POST /api/websites/{id}/checks`. A follow-up is allowed to read a result that was already stored. Starting a new browser check is a different action, and it still belongs on the registry page, where you confirm that you may test the site.

The execution order is `v1`. That pairing is why **Notification draft** can still see the website name after **Latest check** has replaced the current item with the check JSON.

Each HTTP call gives up after 10 seconds. That is enough to read rows. It is not long enough to run Playwright, which is another reason this workflow does not launch a check.

## What you do once

From Ubuntu, in this repository:

```bash
docker compose up -d n8n
```

`docker compose up -d n8n` starts n8n only. `docker compose up -d` with no service name also starts PostgreSQL. Do not add `-v`. That flag deletes the named volumes, including the Sentinel database and n8n's own database.

Import the workflow. The container user is `node`. The JSON is mounted at `/files`.

```bash
docker compose exec -u node n8n n8n import:workflow --input=/files/failed-check-follow-up.json
```

Import leaves the workflow inactive. Open `http://localhost:5678`. The first visit asks you to create the n8n owner. That account unlocks the n8n editor. It is not a Sentinel user, and Sentinel still has no login.

In the workflow, choose **Execute workflow**. The execution shows one **Notification draft** item for each website whose newest check failed. If the website list is empty, the run finishes at **List websites**. If every latest check succeeded, or no check has been stored, **Notification draft** has no items. Either one is a completed run with nothing to send.

You can also execute from the CLI without opening the editor. Stop the long-running n8n container first so the one-off process can bind the task broker port, then start n8n again:

```bash
docker compose stop n8n
docker compose run --rm -T -u node --no-deps --entrypoint n8n n8n \
  execute --id=7c2a9b10-1d4e-4f6a-8b3c-11aa22bb3301 --rawOutput
docker compose up -d n8n
```

`--entrypoint n8n` is required. Without it, Compose treats `n8n` as an unknown command inside the image entrypoint. A successful failed-check run ends with `lastNodeExecuted` set to **Notification draft** and a draft object that includes `website_name`, `base_url`, `outcome`, `http_status`, `error_message`, and `checked_at`.

If the container cannot open the API, edit **API address** and run it again. On this machine `host.docker.internal` is Ubuntu's Docker bridge, `172.17.0.1`. A request from n8n reached a program listening on Ubuntu port 8000. The API you start from PowerShell on `127.0.0.1` is not that address. A request toward the Windows host address timed out. Run the API on Ubuntu when you want the workflow to call it. The Windows virtual environment does not run there. An Ubuntu bind of `0.0.0.0:8000` is still reachable from Windows at `http://127.0.0.1:8000` through the same WSL port forward that publishes Postgres, so Next.js can keep using localhost while n8n uses `host.docker.internal`.

## What this leaves open

- No message leaves the machine. Replace **Notification draft** when you choose a destination.
- Nothing runs on a timer. A schedule can be added in n8n later. It should keep reading stored checks until you deliberately decide that a schedule may start a browser.
- No OpenAI call. When a key exists, an explanation can be added to the draft. The draft does not need that field to be useful.
- No Sentinel authentication. Anyone who can reach the API can read the same rows the workflow reads. A later account system will mean this workflow needs a credential. Do not invent a user on the website row to pretend that already happened.
- n8n is not a queue for Playwright. A check still runs inside the API request. This workflow avoids that wait by not starting a check.

## Mistakes

- Treating the n8n owner as a Sentinel account. The owner can edit workflows. The API still does not know who they are.
- Pointing **API address** at `http://localhost:8000` from inside the container. That address is n8n, or nothing, on port 8000.
- Activating a schedule that posts a browser check for every website. The follow-up file does not do that. Adding it later is a product decision, because a check still requires permission to test the site.
- Giving the n8n container `DATABASE_URL`. It does not need Sentinel's password, and a workflow that can read the container environment could then read that password.
- Running `docker compose down -v` to "reset n8n". The same flag deletes `sentinel_sentinel_postgres_data`.
