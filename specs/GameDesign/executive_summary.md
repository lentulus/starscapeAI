# StarscapeAI — Executive Summary
*Internal design blog · Draft 1 · April 2026 · AI authored from developer concepts*

---

## What This Is

StarscapeAI is a fully autonomous 4X space civilisation simulator. It is not a playable game. There is no player, no win condition, and no runtime interface. The simulation runs as a background process and produces history — a record of what a small number of sophont species did to each other and to the galaxy over roughly forty thousand simulated years. An LLM serves as historian, distilling that record into narrative; interested humans are the audience. There is also early-stage interest in using the generated history and setting as a substrate for an RPG campaign.

---

## The Physical Stage

The simulation takes place inside a 2,000-parsec cube of real stellar data drawn from the Hipparcos catalogue — roughly 2.47 million stars, with spectral types, physical parameters, and companion star populations derived from the raw photometric data using established astrophysical methods. Every star system with potentially habitable bodies has had its planetary population procedurally generated and its surface and atmospheric conditions computed.

---

## Several Species, One Starting Gun

The exact species count is still being finalised — the current design targets around six civilisation-starting species, with eleven sophont species hand-authored in the spec in total. All of them begin the simulation simultaneously at interplanetary tech level — spacefaring within their home systems, but not yet capable of reaching other stars. They do not know each other exists. Each species has distinct biological, psychological, and social traits that shape how it researches technology, organises politically, wages war, and reacts to contact — and all apply the same habitability criteria to the same worlds, so competition over prime real estate is structural. Conflict will emerge from geography and scarcity, not from a trigger.

---

## The Record and the Historian

Every significant event is logged at weekly tick resolution — asset movements, combat outcomes, political decisions, first contacts, species milestones. During quiet periods, monthly summary records are acceptable to reduce volume. The log is designed so that an LLM historian can reconstruct causality: not just what happened, but why, in what order, and what alternatives existed.

The historian's role is to identify decisive points — the moments where the trajectory of a species or a conflict changed. This requires that the event log captures enough context per record for the Historian to assess counterfactuals. Log design is a first-class design concern, not an afterthought.

---

## Where We Are Now

The stellar catalog is complete — star positions, spectral types, and physical parameters are all populated. Full pre-computation of binary star orbits and planetary bodies across 2.47 million systems proved too non-performant; the approach has shifted to incremental generation at the point of exploration, producing system detail only when a species reaches it. Biosphere design is the next step.

The species layer is designed but not yet implemented — eleven species entries — AI authored from developer concepts — are complete in the spec, blocked on controlled vocabulary finalisation before the database schema can be written. The civilisation layer has not been started. It is the next major phase.

The immediate dependency chain is: finalise species vocabulary → write Species schema → seed the eleven species → implement Biosphere and SophontPresence tables → begin Polity and tech tree implementation → design the simulation tick loop.

---

*Next: to be expanded as design decisions are finalised.*
