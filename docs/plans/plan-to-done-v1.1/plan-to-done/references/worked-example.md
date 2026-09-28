# Worked example: write a connected change plan

This is an illustrative specification fragment, not a live RestoreAssist audit, an approved
product requirement, a test result or a claim about the current application.

## Request

An administrator needs to save incomplete client intake information, return to it later and
continue the authorised process without inventing unavailable answers.

## Scope interpretation

This request covers intake behaviour and its affected downstream interfaces. It does not,
by itself, authorise redesigning billing, dispatch or the whole CRM. The planner still checks
whether intake depends on those capabilities and records any wider product-completion gaps.

## Examples of written requirements

REQ-01: The authorised administrator can save an intake draft when designated optional
initial fields are empty. The precise field list is taken from the approved intake rules;
unknown field classifications are a blocking business decision, not invented by the planner.

REQ-02: Reopening the saved draft shows the values most recently confirmed as saved, including
the distinction between an empty value and an intentionally removed value where relevant.

REQ-03: Progressing beyond draft applies the rules for the destination state rather than
silently removing those rules to allow incomplete intake.

REQ-04: A failed save leaves the entered information recoverable through the agreed client
behaviour and presents a visible failure state. The recovery mechanism and limits require
an engineering decision before implementation.

## Interface and handoff questions to resolve

Where is draft state stored? Which existing route or service owns it? What permission checks
apply? How are concurrent edits handled? What does the UI display before, during and after
saving? Which downstream state accepts a draft and which requires completed information?
Existing implementation and rules should answer these before the founder is asked.

## Example vertical work package

WP-INTAKE-01 connects the existing draft UI, persistence interface and reopening behaviour.
Inputs are the accepted field/state rules and an evidenced current architecture. Reuse the
existing autosave/persistence capability where verified. Required output is the connected
behaviour described by REQ-01 and REQ-02, not merely a new button.

Planned checks include a normal draft, incomplete input, failed save, reopened record,
unauthorised access, repeated submission and a conflicting edit where applicable.
An independent reviewer checks the same candidate and the coverage of the test procedure.
The package cannot silently replace the existing validation rules or create a second store.

## Example acceptance case

Given an authorised test administrator and the agreed incomplete fixture, save the draft,
close the view, reopen the record and compare persisted values with the fixture. Verify that
progression to a restricted downstream state still applies its own validation. A save toast
or successful HTTP response alone does not pass this case.

## How the planner reports the wider project

The intake change can be fully planned while dispatch remains an unverified dependency or
an out-of-change-scope product gap. The report names that gap and the decision required.
It does not say that the CRM is complete, and it does not add a dispatch rebuild without
approval. Planning is complete only at the explicitly stated planning boundary.

## TypeSafe relevance

Jev is not needed to determine an exact field rule, compare saved values or grant access.
A later, separately approved advisory use could rank suitable planning skills. The entire
intake specification remains writable when Jev is disabled.
