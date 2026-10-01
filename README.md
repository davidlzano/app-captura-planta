# Shop-Floor Data Capture App

![Architecture](docs/architecture.png)

Web form for hourly production logging on gluing machines, used from a phone by the floor inspectors. It replaces paper logging followed by later keying-in with validated capture at the moment of the event.

This repository is a **demo reimplementation** of one of three applications I developed and run in production. The code published here is original, uses synthetic data, and contains no company information.

---

## The problem

Production was logged on paper during the shift and someone keyed it in afterwards. That creates three chained problems:

- **Double work**: it is written once by hand and again on the computer.
- **Latency**: hours or days pass between something happening on the floor and the data existing.
- **Errors that cannot be corrected**: when the person keying in finds an inconsistency, the shift is over and there is nobody to ask.

Capturing at the source solves all three. But it introduces a new one: the form has to work on a phone, on the factory floor, possibly with gloves on, for someone who has other things to do.

## The central design decision

**The operator enters the machine's counter reading, not the hour's production.**

It looks like a detail and it is not. Asking someone to mentally subtract the previous reading every hour, on the floor and in a hurry, is exactly where errors creep in. Copying a number from a screen is not.

The system calculates production by subtracting what that operator has already logged, on that order and that machine, during the day:

```
counter reading        8,200
already logged         5,000
                     ────────
hour's production      3,200
```

When the operator, the order or the shift changes, the accumulated total resets to zero, so the next entry becomes a new baseline without anyone having to say so.

The form shows the calculation **before** saving. Without that, someone who enters 12,400 does not understand why the history shows 800, and distrust of the system is costlier than any keying error.

---

## Technical decisions

**The write lock is not decorative.** Reading the accumulated total and writing the record have to be a single atomic operation. If two inspectors save at the same time on the same order, both would read the same total and the second would miscalculate their production.

**Catalogs reload on their own.** A daemon thread refreshes orders, events and operators every hour. When the ERP creates a new order, it shows up in the form without restarting the service and without anyone having to log into the server.

**If the database fails, the app keeps serving.** The reload keeps the data already in memory instead of emptying it. A floor app without catalogs stops working entirely; one working with data from an hour ago is still useful.

**Anti-cache headers.** This stopped being theoretical in production: after updating the form, devices kept showing the previous version for hours.

**The server does not trust the form.** The form validates for the user's convenience; the server validates because it is the only real guarantee. It checks that the order exists and is active, that the machine is valid, and that the required fields are complete.

**Diagnostic endpoints.** `/api/estado` reports when the catalogs were loaded and how many records there are; `/api/recargar` forces a refresh. They let you verify the service without logging into the server, which on the floor is the difference between fixing something in a minute or in half an hour.

---

## Interface design

The context of use outranks any aesthetic preference:

- Touch targets of at least 56px, because it is operated with gloves
- High contrast, because floor lighting is uneven
- The counter reading in large, tabular type, so that a keying error is noticed before saving
- The quantity field disappears when the event is not a production run, because a stoppage produces no units
- Messages say what happened and what to do, they do not apologize

---

## Running it

Requires Python 3.10 or higher.

```bash
pip install -r requirements.txt

python datos_demo.py   # creates planta.db with example catalogs
python app.py          # server at http://localhost:5000
```

To try it from a phone, with both devices on the same network, go to `http://<computer-ip>:5000`.

Test flow: select a machine, type an order from the catalog (`OP-2601` onward), choose an operator and a production-run event, and enter a reading. Save, then enter a higher reading: the second record will show only the difference.

---

## Structure

| File | Contents |
|---|---|
| `app.py` | Routes, server validation, anti-cache headers |
| `data_manager.py` | In-memory catalogs, hot reload, production calculation |
| `datos_demo.py` | Generates the database with example catalogs |
| `templates/form.html` | Mobile form |

---

## Differences from the production version

| | Here | Production |
|---|---|---|
| Orders | Local SQLite | SQL Server, fed by the ERP pipeline |
| Events and operators | Local SQLite | Excel master files maintained by quality |
| Destination | SQLite | Consolidated in Excel on a network folder |
| Authentication | operator selector | validation by national ID number against the master file |
| Deployment | manual | service on a floor computer, automatic start |

It is one of three sibling applications with the same architecture, each for a different plant process.

---

## Possible extensions

- Local queue to log offline and sync when the network returns
- Alert when a reading is lower than the accumulated total, which indicates a counter change or a keying error
- Shift close-out with a per-operator summary

---

## License

MIT
