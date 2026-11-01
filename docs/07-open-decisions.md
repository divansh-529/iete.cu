# 07 — Open Decisions (blueprint §21)

Each item has a **recommended default** so that development can start straight away. Every one of them is stored in `settings` or as data, so changing a decision later does not require a code change. Tick each box once the Chairperson confirms it.

## Organisation
- [x] **Final org chart.** Decided 2026-11-01: the Vice Chairperson and Secretary are equals reporting to the Chairperson; the Joint Secretary and the department Leads report to the Secretary. Departments and Lead positions are created and removed by the Chairperson in the portal. *Still to provide:* member names.
- [ ] **Terms.** The default is one term per academic year (July–June). Leaderboards and history are grouped by term.

## Accounts & auth
- [x] **First-login credentials.** Decided 2026-11-01: every new account starts with the forum's default password (`CU@12345678`, configurable), sent to the member's Gmail on approval; they must change it at first sign-in. Invite links and custom temporary passwords remain available to the Chairperson.
- [x] **Recruitment.** Decided 2026-11-01: Leads (own department), the Vice Chairperson and the Secretary propose members; the Chairperson, Vice Chairperson or Secretary approve. See [02-permissions.md](02-permissions.md).
- [ ] **Session length.** The default is a 2-hour idle timeout and a 7-day absolute timeout.
- [ ] **Lockout.** The default is a 15-minute lockout after 5 failed logins in 15 minutes.
- [ ] **MFA.** The default is not at launch. Optional TOTP for the Chairperson and Treasurer comes later.

## Permissions
- [ ] **Default grants.** The default is the table in [02-permissions.md](02-permissions.md) §8.
- [ ] **Who else can manage permissions?** The default is the Chairperson only. Others can receive `permissions.manage` explicitly, subject to the delegation ceiling.

## Points
- [ ] **Combining evaluator scores.** The default is **sum**, matching the 10 + 8 = 18/30 example in the blueprint. The choice is configurable per evaluation (`sum` / `average` / `separate`).
- [ ] **Maximum points per event.** The default is 30 per evaluatee, set per event when evaluations are opened.
- [ ] **Evaluator map.** The default is that the Vice Chair evaluates Leads and the Secretary evaluates Leads and members. *To provide:* the actual mapping.
- [ ] **Evidence required?** The default is that remarks are required and evidence is optional.
- [ ] **Do completed tasks give points automatically?** The default is no, as the blueprint states.

## Finance
- [ ] **Accounts.** The default is Main Society Account, Membership Fund, Event Fund and Sponsorship Fund.
- [ ] **Who records income?** The default is the Treasurer.
- [ ] **Expense workflow.** The default is submit → Treasurer verifies → Vice Chair or Chairperson approves → posted. Amounts above ₹5,000 need the Chairperson.
- [ ] **Reconciliation frequency.** The default is monthly, done by the Treasurer.
- [ ] **Opening balances.** *To provide:* the balance of each account as of the go-live date.

## Membership
- [ ] **Categories and fees.** *To provide.* The placeholder is "Student Member", ₹X.
- [ ] **Renewal.** The default is annual, valid until the end of the term.
- [ ] **Payment modes.** The default is cash, UPI and bank transfer, with the payment reference and proof recorded. The site does not take payments online.
- [ ] **Refunds.** The default is that the Treasurer records a refund as a status change plus a linked expense entry.

## Participants
- [ ] **Account vs. account-less registration.** The default is that **participant accounts are required**, so that participants can view their status and certificates. This can be switched per event.
- [ ] **Required fields.** The default is name, UID, email, phone, department, year and consent.
- [ ] **Privacy notice.** *To draft:* what is collected, why, who can see it, and the retention period (default: 1 year after the event, then anonymised).

## Documents
- [ ] **Allowed formats.** The default is PDF, DOCX, XLSX, PPTX, JPG, PNG and ZIP.
- [ ] **Size limit.** The default is 15 MB per file, or 5 MB for images, to protect the free storage tier.
- [ ] **Deletion.** The default is that only users with `documents.delete` can delete, and only as a soft delete. Files are purged after 90 days.
- [ ] **Default document access.** The default is Chairperson, Vice Chair, Secretary and Joint Secretary on all event folders, with others given access per folder.

## Notifications
- [ ] **Email?** In-app notifications for everything; **email for new-member sign-in details** through Resend's free tier (`IETE_RESEND_API_KEY`). Until a key is set, approvers are shown the details to pass on by hand.

## Deployment assumptions
- [ ] **Volumes.** These are used to size the free tiers. *To confirm:* team ~60–80, roughly 10–20 events a year, up to 500 participants per event, under 5 GB of files a year.
