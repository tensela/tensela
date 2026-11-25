# Security

Tensela runs on your computer, and Tensela itself does not connect to the internet. Even so, a program can have a
weakness: a project file made to do harm when it is opened, a way out of the limits of the Code node, an extension
that gets more than it asked for.

## Reporting a problem

If you find one, please do not publish it in an issue or a discussion. Write to **contact@tensela.com** with:

- what the problem is and what someone could do with it;
- how to see it happen (a project file, the steps, the version of Tensela);
- whether you want your name in the note of the fix.

An answer usually comes within a week. Once it is fixed, the release notes say what was fixed and thank whoever
found it, if they want.

## Versions

Fixes go into the latest version. Download it from [tensela.com/download](https://tensela.com/download/).

## Checking a download

Each release comes with `SHA256SUMS`, the fingerprints of its files, and `SHA256SUMS.minisig`, their signature, made
with a key that only whoever publishes Tensela has. The public key is `tensela.pub`, in this repository, and the
Download page shows how to check both.

## Extensions

Each extension is a program by its own author. A problem in an extension goes to that author, through the links of
its card. If the extension is in the catalogue of tensela.com, write to contact@tensela.com too, so it can be taken
out of the catalogue until it is fixed.
