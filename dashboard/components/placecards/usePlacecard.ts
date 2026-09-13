"use client";

import { useCallback, useMemo, useState } from "react";
import {
  applyAdvance,
  applyDecision,
  applySketchSave,
  appendUnique,
  canAdvance,
  remainingGates,
  seedCard,
  type Placecard,
} from "@/lib/placecards/model";

export function usePlacecard() {
  const [card, setCard] = useState<Placecard>(seedCard);
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState("intake");
  const [fenceDraft, setFenceDraft] = useState("");
  const [schemaDraft, setSchemaDraft] = useState("");
  const [gherkinDraft, setGherkinDraft] = useState("");
  const [promiseDraft, setPromiseDraft] = useState("");
  const [decisionGo, setDecisionGo] = useState(false);
  const [decisionReason, setDecisionReason] = useState("");

  const remaining = useMemo(() => remainingGates(card), [card]);
  const advanceEnabled = canAdvance(card);

  const openCard = useCallback(() => setOpen(true), []);

  const patchAnswers = useCallback((key: keyof Placecard["answers"], value: string) => {
    setCard((current) => ({
      ...current,
      answers: { ...current.answers, [key]: value },
    }));
  }, []);

  const setAppetite = useCallback((value: string) => {
    setCard((current) => ({ ...current, appetite: value }));
  }, []);

  const addFence = useCallback(() => {
    setCard((current) => ({ ...current, fences: appendUnique(current.fences, fenceDraft) }));
    setFenceDraft("");
  }, [fenceDraft]);

  const addSchema = useCallback(() => {
    setCard((current) => ({
      ...current,
      schemaLines: appendUnique(current.schemaLines, schemaDraft),
    }));
    setSchemaDraft("");
  }, [schemaDraft]);

  const addGherkin = useCallback(() => {
    setCard((current) => ({ ...current, gherkin: appendUnique(current.gherkin, gherkinDraft) }));
    setGherkinDraft("");
  }, [gherkinDraft]);

  const addPromise = useCallback(() => {
    setCard((current) => ({ ...current, promises: appendUnique(current.promises, promiseDraft) }));
    setPromiseDraft("");
  }, [promiseDraft]);

  const setGoalArmed = useCallback((armed: boolean) => {
    setCard((current) => ({ ...current, goalArmed: armed }));
  }, []);

  const advance = useCallback(() => {
    setCard((current) => applyAdvance(current));
  }, []);

  const saveSketch = useCallback(() => {
    setCard((current) => applySketchSave(current));
  }, []);

  const recordDecision = useCallback(() => {
    setCard((current) => applyDecision(current, decisionGo, decisionReason));
  }, [decisionGo, decisionReason]);

  return {
    card,
    open,
    tab,
    setTab,
    fenceDraft,
    setFenceDraft,
    schemaDraft,
    setSchemaDraft,
    gherkinDraft,
    setGherkinDraft,
    promiseDraft,
    setPromiseDraft,
    decisionGo,
    setDecisionGo,
    decisionReason,
    setDecisionReason,
    remaining,
    advanceEnabled,
    openCard,
    patchAnswers,
    setAppetite,
    addFence,
    addSchema,
    addGherkin,
    addPromise,
    setGoalArmed,
    advance,
    saveSketch,
    recordDecision,
  };
}
