---
title: Publish an extension
description: Put it on the Extensions page of tensela.com, update it, and check the .zip you download.
---

## What for

So that anyone finds it on the [Extensions page](/extensions/) of tensela.com, with its card, what it may do, its
`.zip` and its fingerprint.

## How

1. **Its code, in a public repository.** The catalogue asks for it: anyone can read what it does.
2. **A release with its `.zip`.** With the template, tag the version (`git tag v0.1.0`, `git push --tags`): its
   workflow runs the tests, packs it and attaches the `.zip` and `SHA256SUMS`.
3. **Its file for the catalogue**, made from the `.zip` with the tool of the repository
   [tensela-extensions](https://github.com/tensela/tensela-extensions):

   ```bash
   python tools/catalogue.py entry facade-tools-0.1.0.zip https://github.com/…/facade-tools-0.1.0.zip > extensions/facade-tools.json
   ```

   It copies what its card says and computes its fingerprint. Read it: it is what the page shows.
4. **A pull request** with that file. A check runs by itself (the `.zip` is the one its fingerprint says, and its card
   agrees with its file), and then a person reviews it.

## What is reviewed

- Its code is public, and the `.zip` has what that code says.
- Its permissions make sense for what it does, and each one says why.
- Nothing hidden: no code downloaded while it runs, no data of the person sent anywhere without saying so, nothing
  obfuscated.
- Its card is complete: name, what it does, who makes it, licence, code, where to report a problem.

The problems of an extension are reported where its card says, to whoever makes it.

## Update it

Change `version` in its card, tag the new release, and a pull request that changes `version`, `download`, `sha256`
and `updated` in its file. Whoever installs the new `.zip` sees «It updates the one installed».

## Check a .zip you downloaded

Its page on tensela.com says its fingerprint (SHA-256). In a terminal:

```bash
sha256sum facade-tools-0.1.0.zip
```

If the 64 characters are the same, the `.zip` is the one that was reviewed.
