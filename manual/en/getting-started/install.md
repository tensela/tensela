---
title: Install
description: How to download and open Tensela on Linux.
---

:::note
The first version of Tensela is on its way. These are the steps it will have.
:::

Tensela comes as a single file, an **AppImage**: usually nothing to install and nothing to set up. There is also a
[portable folder](#the-portable-folder). Before you start, check
[What you need](/manual/getting-started/requirements/): a 64-bit Linux PC with 4 GB of memory is enough.

1. **Download** the file `Tensela-….AppImage` from the [Download](/download/) page.
2. **Allow it to run:** right-click the file, open **Properties**, and turn on **Allow executing file as program**.
   From a terminal: `chmod +x Tensela-*.AppImage`.
3. **Open it** with a double-click. The first time, Tensela offers to put itself in the **applications menu** of your
   desktop, with its icon, and to open `.tela` files with a double-click. If you say no, it is in **Preferences →
   General → Applications menu**.

## The portable folder

For whoever cannot use an AppImage, or wants it in `/opt`: the same Tensela as a folder, in `Tensela-….tar.gz`.

1. **Unpack it** wherever you like (right-click → Extract here, or `tar -xzf Tensela-*.tar.gz`).
2. **Open it** with `./tensela`, inside the folder.
3. To have it in the menu: **Preferences → General → Applications menu**.

## Check the download

The [Download](/download/) page says the **fingerprint** (SHA-256) of each file, and offers the file `SHA256SUMS`.
With both in the same folder, in a terminal:

```bash
sha256sum -c SHA256SUMS --ignore-missing
```

If it says **OK**, the file is the one that was published.

The fingerprints say the file arrived whole. To know **who published them**, `SHA256SUMS` comes with a signature,
`SHA256SUMS.minisig`, made with a key that only Tensela has. Check it with minisign (`sudo apt install minisign`),
with both files in the same folder. The Download page has the command with the public key already in it, ready to
copy:

```bash
minisign -Vm SHA256SUMS -P <the public key of Tensela>
```

If it says **Signature and comment signature verified**, the fingerprints are the ones Tensela published. The same
public key is in the repository, in `tensela.pub`.

## Your files

- Your projects end in `.tela`. Open them from **File → Open**, or with a double-click once Tensela is in your menu.
- What you design with Tensela is yours: the program's licence (GPL-3.0, free software) covers the program, not your
  projects. Explained in plain words in [Free, offline and yours](/manual/getting-started/free-offline-yours/).

## If it does not open

See [Common stumbles → Installing and opening](/manual/common-stumbles/#installing-and-opening).
