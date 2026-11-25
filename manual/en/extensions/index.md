---
title: Extensions
description: What is added to Tensela without changing it, how to install one, and what each permission means.
---

## What for

An extension adds to Tensela what it does not bring: a node for a system of your office, a way of exporting to the
format of a machine, a panel with a tool, a connection with another program. It is added without changing Tensela, and
it goes away when it is turned off.

## How

1. Find it on the [Extensions page](/extensions/) of tensela.com, or get it from whoever makes it. It is a `.zip`.
2. **Extensions → Manage extensions… → Install from a file…** and choose the `.zip`.
3. Read its card before installing: what it does, who makes it, its licence and **what it can do**. What it does not
   ask for is in green; what it asks for is in amber, each one with **why**, in the words of whoever made it.
4. **Install.** It is on at once: its nodes are in the finder (Tab), its entries in the menus, its panels in the
   **Extensions** menu.

In **Manage extensions…**, each card has its **switch** (on or off, at once) and its **⋯** (its website, where to
report a problem, its code, its folder, Remove). On top, a search, which ones to show and in what order, and two views:
detailed (one card each) and compact (one line each, which opens with a click).

## What it can do

Every extension computes inside Tensela. Besides that, its card says if it may:

| In amber | It means |
|---|---|
| **Internet** | it connects to the internet (to download the weather of a place, a map…) |
| **Files outside the project** | it reads or writes files that are not of the project |
| **Other programs** | it starts other programs of the computer |
| **Talks with other programs of the computer** | another program of the computer talks with Tensela, inside it, never through the internet |

An extension is a program: Tensela shows what it says it does, but cannot check it. Install only those that come from
someone you trust. Those of the Extensions page of tensela.com have their code public and were reviewed by a person
before being published: that lowers the risk, but it is not a guarantee. Install only the ones you need.

## Update one

Install the new `.zip` over it. Its card says what happens: **it updates the one installed** (1.0 → 1.1), **it is
older** (in amber: you go back to an earlier version) or **it is the same**. If it was on, it stays on; if it was
off, it stays off.

## The two of Tensela

- **Animation** comes with Tensela, off. Turned on, **Extensions → Animation** opens its panel: a slider from one value
  to another in a number of frames, the 3D view as it is seen at each one, as a GIF or PNG images.
- **AI connection** comes apart (on the Extensions page). An AI program of your choice looks at the open project and
  changes it. Tensela talks with it inside your computer; what that program does with what it reads depends on it.
  Each step is undone with Ctrl + Z, and Code nodes and files ask you first.

## Tips

- A project with nodes of an extension that is not installed (or is off) opens anyway: those nodes are kept, marked
  in red, and they compute again when the extension is back.
- An extension that fails when it is turned on stays off, and Tensela says why.
- Its panels move and go to a separate window like the others; a separate window stays above Tensela.
- To write your own: [Write an extension](/manual/extensions/write/).
