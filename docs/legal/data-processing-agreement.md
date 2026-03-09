# Data Processing Agreement

**Last Updated:** March 2026

**Effective Date:** March 1, 2026

**Version:** 1.0

## 1. Parties and Definitions

### 1.1 Parties
- **Data Controller:** Customer (as defined in Terms of Service)
- **Data Processor:** Priya AI Technologies ("Company," "we," "us")
- **Sub-processors:** Third-party service providers listed in Section 5

### 1.2 Definitions
- **Personal Data:** Any information relating to an identified or identifiable natural person
- **Processing:** Any operation performed on Personal Data (collection, storage, transmission, etc.)
- **Data Subject:** The individual to whom Personal Data relates
- **Processing Instruction:** Instructions from Controller regarding processing scope and purpose
- **Data Breach:** Unauthorized access, loss, or disclosure of Personal Data
- **GDPR:** General Data Protection Regulation (EU 2016/679)
- **SCCs:** Standard Contractual Clauses approved by the European Commission

## 2. Scope and Purpose

### 2.1 Scope of Processing
This Data Processing Agreement applies to Personal Data processed by the Processor on behalf of the Controller through the Priya Global Platform, including:
- User account information
- Customer contact and communication data
- Business information and configuration data
- Usage analytics and interaction logs
- Payment and billing information
- Any other data provided to or collected through the Service

### 2.2 Processing Purposes
The Processor processes Personal Data solely for:
- Providing the Service as described in the Terms of Service
- Performing obligations under the Processor's subscription agreement
- Conducting technical operations and maintenance
- Ensuring security and preventing fraud
- Complying with legal obligations

### 2.3 Duration
This DPA remains effective for as long as the Controller uses the Service and Personal Data is processed. The DPA survives termination of the underlying Service agreement for data deletion and final compliance activities.

## 3. Processing Instructions

### 3.1 Controller Instructions
- The Processor processes Personal Data only on documented instructions from the Controller
- Instructions include the purpose, scope, nature, and duration of processing
- The Controller is responsible for lawful basis and compliance with data protection laws
- The Controller must ensure prior consent or legitimate basis for all Processing

### 3.2 Lawful Processing
The Controller confirms it has:
- Legal authority to provide Personal Data
- Appropriate lawful basis under GDPR Articles 6 and 9
- Data subject consent where required
- Provided required privacy notices to Data Subjects
- Implemented necessary safeguards

### 3.3 Instruction Modifications
- Controller may modify Processing Instructions via account settings
- Changes effective upon written notice
- Processor implements changes within 30 days where technically feasible
- Emergency instructions regarding data protection honored immediately

## 4. Processor Obligations

### 4.1 Processing Restrictions
The Processor shall:
- Process Personal Data only on documented Controller instructions
- Not process Personal Data for own purposes
- Ensure authorized personnel have confidentiality obligations
- Implement appropriate technical and organizational measures
- Ensure sub-processor compliance with equivalent obligations

### 4.2 Personnel Restrictions
The Processor shall:
- Ensure only authorized personnel can access Personal Data
- Implement access controls limiting exposure to need-to-know basis
- Require confidentiality agreements from all personnel
- Conduct background checks for personnel with access
- Provide security training and awareness programs
- Document personnel access logs

### 4.3 Sub-processor Management
The Processor shall:
- Provide list of authorized sub-processors (Section 5)
- Notify Controller of planned sub-processor additions (30 days notice)
- Allow Controller to object to sub-processor additions
- Ensure sub-processors contractually bound by equivalent obligations
- Remain liable to Controller for sub-processor performance

## 5. Sub-processors and Third-Party Service Providers

### 5.1 Approved Sub-processors
The Controller authorizes the Processor to engage the following sub-processors:

**Infrastructure and Cloud Services**
| Service Provider | Purpose | Location | Category |
|---|---|---|---|
| Amazon Web Services (AWS) | Cloud hosting, data storage, backups | US, EU (optional) | Infrastructure |
| AWS RDS | Database hosting and management | US, EU (optional) | Infrastructure |

**Payment Processing**
| Service Provider | Purpose | Location | Category |
|---|---|---|---|
| Stripe | Payment processing and billing | US (with EU data center option) | Payment |

**AI and Machine Learning**
| Service Provider | Purpose | Location | Category |
|---|---|---|---|
| OpenAI | API calls for language models | US | AI Services |
| Anthropic | API calls for language models | US | AI Services |

**Communication Infrastructure**
| Service Provider | Purpose | Location | Category |
|---|---|---|---|
| Twilio | SMS delivery and messaging | Worldwide | Communications |
| SendGrid | Email delivery | US | Communications |
| Third-party messaging providers | WhatsApp, Telegram, social media | Various | Communications |

**Analytics and Monitoring**
| Service Provider | Purpose | Location | Category |
|---|---|---|---|
| Google Analytics | Aggregated usage analytics | US | Analytics |
| Sentry | Error tracking and monitoring | US | Monitoring |

### 5.2 Sub-processor Additions
- Controller notified 30 days before new sub-processor engagement
- Notification provided via email to registered contact
- Controller may object via legal@priyaglobal.com
- Objection must be submitted within 15 days
- If objection sustained, Controller may terminate without penalty
- New sub-processor not engaged if valid objection received

### 5.3 Sub-processor Obligations
All sub-processors bound by written contracts requiring:
- Processing only on Processor instructions
- Equivalent data protection and security measures
- Obligation to delete or return data post-termination
- Confidentiality of Personal Data
- Cooperation with data subjects and authorities
- Sub-processor chain limited (no onward sub-processing without approval)

## 6. Data Subject Rights Support

### 6.1 Assistance with Rights Requests
The Processor shall assist the Controller in fulfilling data subject rights requests:
- **Right to Access:** Provide requested data in portable format
- **Right to Rectification:** Correct inaccurate or incomplete data
- **Right to Erasure:** Delete data upon proper request
- **Right to Restrict:** Limit processing of data
- **Right to Portability:** Export data in machine-readable format
- **Right to Object:** Respect objections to processing

### 6.2 Rights Request Process
- Data subjects may contact Controller with requests
- Controller forwards request to Processor: dpo@priyaglobal.com
- Processor acknowledges request within 3 business days
- Processor implements request within 30 days
- Processor notifies Controller of completion

### 6.3 Controller Responsibility
- Controller responsible for responding to Data Subjects
- Processor provides supporting information and data
- Controller verifies Data Subject identity
- Controller determines whether request is valid

## 7. Data Security and Protection

### 7.1 Security Measures
The Processor implements comprehensive technical and organizational measures:

**Encryption**
- AES-256 encryption for data at rest
- TLS 1.3 encryption for data in transit
- Encrypted database connections
- Encryption key management and rotation
- Certificate pinning for critical connections

**Access Controls**
- Role-based access control (RBAC)
- Multi-factor authentication (MFA)
- Principle of least privilege
- Regular access reviews and audits
- Immediate revocation upon personnel changes
- API key rotation and management

**Network Security**
- Firewalls and intrusion detection systems
- Web Application Firewall (WAF)
- DDoS mitigation and rate limiting
- Network segmentation and isolation
- Regular vulnerability assessments

**Data Security**
- Encrypted backups with separate key management
- Disaster recovery and business continuity plans
- Data integrity monitoring and checksums
- Audit logging for all access and modifications
- Regular backup restoration testing

**Monitoring and Detection**
- Real-time threat detection and monitoring
- Security information and event management (SIEM)
- Endpoint detection and response (EDR)
- Intrusion prevention systems (IPS)
- Security incident response procedures

### 7.2 Security Audits
The Processor shall:
- Conduct annual third-party security audits
- Perform quarterly vulnerability assessments
- Undergo penetration testing (minimum annually)
- Maintain SOC 2 Type II certification (target)
- Provide audit reports to Controller upon request
- Address security findings within agreed timeframes

### 7.3 Security Standards Compliance
- ISO 27001 alignment for information security
- NIST Cybersecurity Framework implementation
- CIS Controls for critical security controls
- OWASP standards for web application security
- PCI-DSS compliance for payment data

## 8. Data Breach Notification

### 8.1 Breach Notification Obligation
In case of Personal Data breach, the Processor shall:
1. Notify the Controller **within 24 hours** of discovery
2. Provide written notification detailing:
   - Nature and scope of the breach
   - Categories of Data Subjects affected
   - Likely consequences of the breach
   - Measures taken to address the breach
   - Impact assessment for Controller
   - Contact information for further details

### 8.2 Investigation and Remediation
The Processor shall:
- Immediately investigate the breach
- Implement measures to contain and mitigate impact
- Preserve evidence for forensic analysis
- Document breach details and findings
- Identify root cause and implement preventive measures

### 8.3 Controller Notification to Authorities
- Controller responsible for notifying authorities if required
- Processor provides necessary information and cooperation
- Processor assists with data protection authority inquiries
- Processor cooperates in regulatory investigations

### 8.4 Public Disclosure
- Processor will not publicly disclose breach without Controller consent
- Except where required by law or court order
- Processor notifies Controller if legal disclosure is required

## 9. Data Transfer Mechanisms

### 9.1 Standard Contractual Clauses
- Processing involves transfer of Personal Data to countries outside EEA/UK
- Processor implements Standard Contractual Clauses (SCCs) for lawful transfer
- SCCs executed between Processor and sub-processors
- Processor conducts Transfer Impact Assessments (TIA)
- Processor documents lawful transfer basis in writing

### 9.2 Transfer Mechanisms
For international data transfers, the Processor utilizes:
- **Standard Contractual Clauses:** EU Commission-approved transfer clauses
- **Supplementary Measures:** Technical and organizational safeguards
- **Adequacy Decisions:** Where applicable (e.g., EU-US agreements)
- **BCRs:** Binding Corporate Rules for intra-group transfers

### 9.3 Data Residency Options
- Data primarily stored in AWS US regions
- EU customers may request EU data residency
- UK customers may request UK data residency
- Additional fees may apply for regional residency
- Residency requests must be specified at account creation

### 9.4 Third-Country Processing
- Some sub-processors are US-based (OpenAI, Stripe, Twilio)
- Processor ensures adequate safeguards and SCCs in place
- Controller consent required for processing in third countries
- Controller may restrict data sharing with specific sub-processors

## 10. Audit Rights and Compliance Verification

### 10.1 Audit Rights
The Controller shall have the right to:
- Audit Processor compliance with this DPA
- Request documentation of security measures
- Request audit reports and certifications
- Conduct on-site inspections (with 30 days notice)
- Require independent third-party audits
- Review sub-processor compliance

### 10.2 Audit Procedures
- Controller may conduct audits annually
- More frequent audits permitted for cause
- Processor provides cooperation and access
- Audits conducted during business hours
- NDA required for audit team members
- Processor bears cost of routine annual audits
- Controller bears cost of additional/extraordinary audits

### 10.3 Compliance Documentation
The Processor shall provide upon request:
- Security audit reports and certifications
- Data processing inventory and maps
- Sub-processor agreements and obligations
- Personnel confidentiality agreements
- Security training documentation
- Incident response procedures
- Disaster recovery plans

### 10.4 Remediation
- Processor shall address audit findings promptly
- Critical security issues remediated within 30 days
- Non-critical issues remediated within 90 days
- Remediation plans documented and tracked
- Progress updates provided to Controller

## 11. Data Deletion and Return

### 11.1 Data Deletion Upon Termination
Upon termination or expiration of the Service:
1. Processor deletes all Personal Data within **90 days**
2. Deletion is permanent and irreversible
3. Backup copies deleted per retention schedule
4. Deletion certificate provided upon request
5. Sub-processors instructed to delete equivalently

### 11.2 Data Export Before Deletion
- Controller may export data before deletion deadline
- Data available in CSV, JSON, and XML formats
- Export functionality available through account settings
- Processor assists with bulk export upon request

### 11.3 Retention Exceptions
Personal Data may be retained beyond deletion period if:
- Required by applicable law (tax, audit, fraud prevention)
- Subject to legal hold or litigation hold
- Necessary for resolving disputes
- Aggregate and anonymized for analytics (anonymized data not subject to deletion)

### 11.4 Deletion Verification
- Processor provides deletion certification
- Controller may verify deletion through audit
- Independent audit of deletion process available
- Backups verified deleted per retention policy

## 12. Liability and Indemnification

### 12.1 Liability for Breach
- Processor liable for damages caused by unauthorized processing
- Processor liable for breach of DPA obligations
- Processor liable for sub-processor breaches (remains liable to Controller)
- Liability subject to Terms of Service limitation of liability clause

### 12.2 Indemnification
The Processor shall indemnify the Controller from:
- Fines and penalties for Processor's processing violations
- Damages awarded to Data Subjects for Processor's breaches
- Costs of notification and remediation
- Third-party claims arising from Processor's unauthorized processing

## 13. International Compliance

### 13.1 GDPR Compliance
- This DPA satisfies GDPR Article 28 processor requirements
- Processor implements all Article 32 security obligations
- Processor supports all Chapter III rights (Articles 15-22)
- Processor cooperates with supervisory authorities

### 13.2 UK GDPR and DCMA
- UK customers covered by UK GDPR and Data Protection Act 2018
- UK data residency available upon request
- Transfers to UK protected by UK adequacy provisions
- UK GDPR processor obligations met equivalently

### 13.3 Other Regulations
- CCPA compliance for California residents
- PIPEDA compliance for Canadian data
- LGPD compliance for Brazilian data
- Other jurisdictional requirements addressed as applicable

## 14. Dispute Resolution

### 14.1 Dispute Procedures
- Good-faith negotiation within 30 days
- Escalation to executive management if unresolved
- Mediation available for significant disputes
- Legal remedies available per Terms of Service

### 14.2 Supervisory Authority Cooperation
- Processor cooperates with data protection authorities
- Processor provides information and access as required
- Processor does not challenge authority jurisdiction
- Processor assists with investigations

## 15. DPA Modifications

### 15.1 Amendment Rights
- This DPA may be amended by written agreement
- Changes to Standard Contractual Clauses require amendment
- Material changes require 30 days notice
- Changes required by law effective immediately

### 15.2 Version Control
- Current DPA available at [DPA URL]
- Version history maintained
- "Last Updated" reflects recent amendments
- Prior versions available upon request

## 16. Contact Information

**Data Protection Officer**
- Email: dpo@priyaglobal.com
- Postal Address: Priya AI Technologies, DPO, [Address]
- Response time: 5 business days

**Legal and Compliance**
- Email: legal@priyaglobal.com
- Data breach reports: security@priyaglobal.com
- Rights requests: privacy@priyaglobal.com

---

**Priya AI Technologies**
Data Processing Agreement © 2026. All rights reserved.

**Appendices**
- [Appendix A: Standard Contractual Clauses](#) (Available upon request)
- [Appendix B: Sub-processor List](#) (Current list in Section 5)
- [Appendix C: Security and Audit Standards](#)
