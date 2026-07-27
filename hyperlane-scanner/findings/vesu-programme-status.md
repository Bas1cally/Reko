# Where the Vesu programme data came from, and what to do about it

## What I actually used

Not immunefi.com. The source was an unofficial community mirror:

```
github.com/infosec-us-team/Immunefi-Bug-Bounty-Programs-Unofficial
  project/vesu.json
```

cloned at commit dated **2026-07-26** (one day before this was written), commit
message "Projects added or unpaused". Fields as scraped:

```
project          Vesu
slug             vesu
launchDate       2024-07-10
updatedDate      2026-05-27
endDate          null
evaluationEndDate null
inviteOnly       false
immunefiStandard true
maxBounty        100000
kyc              false
assets           11x vesu-v2/src/*.cairo  +  https://vesu.xyz ("Primacy of Impact")
rewards          critical 10,000-100,000 / high 1,000-10,000
```

`IMMUNEFI-TARGET-SCAN.md` carried the caveat "Unofficial data — verify any
target on the official page before investing time." I did not repeat that
warning when Vesu was picked as the target, and I should have. It belonged in
the finding report from the first draft.

## Why it was never verified

`immunefi.com` is blocked by this environment's egress policy — the same block
that stops every Starknet RPC, Voyager, Starkscan and `docs.vesu.xyz`. All
return `000` (CONNECT tunnel failed, gateway 403). There was no point at which
the live listing could have been checked from here.

## Why the page may be erroring

The mirror says the programme is live and public; the observed symptom says
otherwise. Plausible explanations, roughly in order:

1. **Switched to invite-only or private.** Immunefi returns an error or a login
   wall for non-invited users. The mirror's `inviteOnly` flag can lag a change
   like this.
2. **Paused or closed since the last scrape.** The mirror tracks pause state in
   its commit messages, and Vesu is still present in the newest commit — but
   this is scraped data, not authoritative.
3. **Stale link.** If the click came from Vesu's own docs or blog, that link may
   point at an old slug or an old URL shape. The canonical form is
   `immunefi.com/bug-bounty/<slug>/information/`.
4. **The programme moved off Immunefi** — to Cantina, Sherlock, or in-house.

## What is not in doubt

Vesu's own published disclosures (which you supplied) reference the programme
three separate times, including paying whitehats through it:

> "Vesu runs a bug bounty program on Immunefi offering a total bounty of
> $100,000." — 2024-12-03 Fee Accounting Disclosure, repeated verbatim in the
> 2024-12-03 Share Inflation Disclosure
>
> "The vulnerability was reported on May 23, 2025 through Vesu's Immunefi bug
> bounty program." — 2025-06-04 Rounding Convention Disclosure

So the programme was real and paying as of mid-2025. Whether it is still open
today is the only open question.

**And the finding itself is independent of all of this.** It is a reproducible
defect in contracts that are deployed and holding funds. The worst case is that
it has to be reported through a different channel for a different reward, not
that it stops being a defect.

## What to do

1. **Log in to Immunefi and search its programme list for "Vesu."** A private or
   invite-only programme is invisible while logged out. Also try the canonical
   URL directly: `https://immunefi.com/bug-bounty/vesu/information/`.
2. **If it is gone, mail `security@vesu.xyz`.** That address is named in Vesu's
   own 2025-06-04 disclosure as the security contact, alongside their Telegram
   and Discord. Send the report there and ask which programme is current. A
   protocol that has publicly paid three whitehats and documented each one is
   not a bad bet for handling a fourth properly.
3. **Do not sit on it while you work this out.** Disclose to the vendor first;
   the platform question can be settled in the same thread.

## Method note

Same failure mode as the Hyperlane episode, one layer up. There the scope was
checked but only after the work; here the programme's *existence* was taken from
a mirror and never re-verified against the source, and the caveat that was
written down once was not carried into the document that would actually be acted
on. Verify the target's existence and scope at source **before** the deep work,
and repeat the caveat in every artefact that depends on it — not only in the
document where the caveat was first discovered.
