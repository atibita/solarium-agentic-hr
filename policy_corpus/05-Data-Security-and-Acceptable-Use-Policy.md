SOLARIUM INC.
Data Security and Acceptable Use Policy
Document ID: SOL-SEC-401 | Version 4.0 | Effective: January 1, 2026 | Owner: Chief Information Security Officer | Classification: Internal — All Employees, Contractors, and Vendors with System Access

---

# 1. Purpose and Scope

This policy sets minimum security requirements for anyone who accesses Solarium systems, networks, or data, including regular employees, interns, contractors, and third-party vendors. It applies to company-owned devices, personally owned devices used for work ("BYOD"), and cloud services used to store or process Solarium or customer data. Violations may result in access revocation, disciplinary action up to and including termination, and — where data was mishandled unlawfully — referral to legal authorities.

# 2. Data Classification

Solarium classifies data into four tiers. Handling requirements scale with sensitivity.

| Tier | Examples | Handling Baseline |
|---|---|---|
| **Public** | Marketing materials, published job postings | No restrictions on sharing |
| **Internal** | Org charts, internal wikis, non-sensitive meeting notes | Share only within Solarium and authorized contractors |
| **Confidential** | Financial forecasts, source code, contracts, employee PII | Encrypt in transit and at rest; share only with people who have a business need |
| **Restricted** | Customer payment data, health information, authentication secrets, legal-hold material | Encrypt in transit and at rest; access logged and reviewed quarterly; sharing requires explicit approval from the data owner |

When in doubt about a document's classification, treat it as Confidential until confirmed otherwise. Do not downgrade a classification level yourself to make sharing more convenient.

# 3. Account and Password Requirements

- **Single sign-on (SSO)** is mandatory for all supported business applications. Do not create local accounts for services that support SSO without Security approval.
- **Multi-factor authentication (MFA)** is required on all accounts that support it, including email, SSO, VPN, and cloud infrastructure consoles. Use an authenticator app or hardware key; SMS-based MFA is discouraged and disallowed for Restricted-tier systems.
- **Passwords**: minimum 14 characters for standard accounts, 16 characters for administrative or infrastructure accounts. Use a password manager (Solarium provides a company-wide license) rather than reusing or memorizing passwords.
- **Shared accounts** are prohibited except for a documented, Security-approved service account with a named human owner.
- Report a suspected compromised credential immediately per Section 8 — do not wait to see if anything bad happens first.

# 4. Device Security

## 4.1 Company-Issued Devices
- Full-disk encryption, endpoint detection software, and automatic OS/security updates are enabled by IT before a device is issued and must not be disabled.
- Devices must be locked (screen lock) whenever unattended, with an auto-lock timeout of 10 minutes or less.
- Only install software from the approved catalog or through an IT-approved request; unapproved software, especially anything requiring elevated/admin privileges, is not permitted without a ticket and Security review.
- Do not disable or "temporarily pause" the endpoint agent, VPN client, or firewall, even to troubleshoot — contact IT instead.

## 4.2 Personal Devices (BYOD)
Personal devices may be used to check email and calendar via the approved mobile app, which enforces a passcode and remote-wipe capability for the work profile only (personal data is never touched). Personal devices may **not** be used to access Confidential or Restricted data, to store company files locally, or to run production infrastructure tools, without a documented BYOD exception approved by Security.

## 4.3 Lost or Stolen Devices
Report a lost or stolen device — company-issued or BYOD enrolled in the work profile — to IT Security within 1 hour of discovery, or as soon as reasonably possible outside business hours via the 24/7 security hotline. Do not wait until your next workday.

# 5. Acceptable Use

Company systems are provided for business purposes. Limited, reasonable personal use (checking personal email, brief personal calls) is fine and does not need to be justified, as long as it does not interfere with your work, consume significant resources, or violate any other part of this policy. The following are never acceptable on company systems or networks, regardless of device:

- Accessing, storing, or transmitting illegal content
- Attempting to access data, systems, or accounts you are not authorized to use, even "just to see if you can"
- Installing or using tools designed to circumvent security controls (unauthorized VPNs/proxies to bypass monitoring, credential-scraping tools, unlicensed penetration-testing tools without a signed authorization)
- Running cryptocurrency mining software
- Using company resources for an outside business, political campaign, or unrelated commercial venture
- Sending Confidential or Restricted data to a personal email account or personal cloud storage, even "to work on it at home" — use the approved remote access tools instead

# 6. AI Tools and Data Handling

Solarium permits use of approved AI assistants (listed on the internal tools portal) for drafting, coding assistance, and research. When using any AI tool, including approved ones:

- Do not paste Restricted-tier data (customer PII, payment data, credentials, health data) into any AI tool, including Solarium's own approved assistants, unless that specific tool has been certified for Restricted data by Security (check the tools portal — certification is listed per tool).
- Confidential-tier data (source code, financial figures, contract terms) may only be used with AI tools that are on the approved list; unapproved public AI chat tools are not permitted for any Confidential or Restricted data.
- Do not use AI-generated code or content in a customer-facing or production system without the same code review and QA process required for any other contribution.

# 7. Remote Access and Network Security

- Use the company VPN when accessing internal systems from outside the office, unless the system is specifically designed for direct secure access (check with IT).
- Public Wi-Fi (cafes, airports, hotels) may be used with the VPN active; avoid conducting sensitive business (e.g., wiring approvals, viewing Restricted data) over public Wi-Fi even with a VPN if you can reasonably wait.
- Home network devices (routers) should use WPA2 or WPA3 encryption and a non-default administrator password. IT does not manage home network hardware but can advise on secure configuration.

# 8. Incident Reporting

**Report immediately — do not delay to investigate first, and do not attempt to "fix it yourself" for anything beyond your own account.**

| Situation | Action |
|---|---|
| Suspected phishing email | Use the "Report Phishing" button in the email client, or forward to security@solarium.example |
| Lost/stolen device | IT Security within 1 hour, or the 24/7 hotline after hours |
| Suspected account compromise | Change your password immediately via the password manager, then report to security@solarium.example |
| Accidental data exposure (e.g., sent Confidential data to wrong recipient) | Report to security@solarium.example within the same business day — early reporting significantly reduces impact and is never itself a disciplinary event |
| Suspicious activity on a system you administer | File a Security ticket marked "Urgent" |

There is no penalty for reporting a good-faith mistake promptly. The only security-related disciplinary risk is failing to report, attempting to conceal an incident, or repeated willful disregard of these controls after being made aware of them.

# 9. Departing Employees and Contractors

Access to all systems is revoked on an employee's last working day, coordinated between IT and People Operations as part of offboarding. Departing employees must return all company devices and physical access badges by their last day (or ship them back within 5 business days for remote employees, using the prepaid label provided by IT). Do not retain copies of any company data, including in personal notes apps, personal cloud storage, or personal email, after departure.

# 10. Policy Exceptions

Any exception to this policy (for example, an unapproved tool needed for a specific project) must be requested in writing to security@solarium.example, reviewed by Security, and time-boxed with a defined expiration date. Verbal approval from a manager does not constitute a security exception.

---
*Related documents: SOL-OPS-202 (Equipment and IT Asset Policy), SOL-HR-105 (Workplace Conduct and Anti-Harassment Policy).*
