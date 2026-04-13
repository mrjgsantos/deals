import { useState } from "react";

import type { UserPreferences } from "../types";

const PREFERENCE_OPTIONS = ["Tech", "Gaming", "Home", "Fitness", "Lifestyle"];
const BUDGET_OPTIONS: Array<{ value: "low" | "medium" | "high"; label: string; hint: string }> = [
  { value: "low", label: "Low", hint: "Prefer lower-cost everyday wins" },
  { value: "medium", label: "Medium", hint: "A balanced mix of value and upgrades" },
  { value: "high", label: "High", hint: "Show bigger-ticket upgrades too" },
];
const INTENT_OPTIONS: Array<{ value: string; label: string; hint: string }> = [
  { value: "save_money", label: "Save money", hint: "Show sharper discounts first" },
  { value: "discover_products", label: "Discover products", hint: "Surface more new things to try" },
  { value: "upgrade_life", label: "Upgrade life", hint: "Lean into useful lifestyle improvements" },
  { value: "practical", label: "Practical", hint: "Bias toward useful day-to-day buys" },
];

export function PreferencesOnboardingPage({
  initialPreferences,
  isSaving,
  error,
  onSave,
  onSkip,
}: {
  initialPreferences: UserPreferences;
  isSaving: boolean;
  error: string | null;
  onSave: (preferences: {
    categories: string[];
    budget_preference: "low" | "medium" | "high" | null;
    intent: string[];
    has_pets: boolean;
    has_kids: boolean;
    context_flags?: Record<string, boolean>;
  }) => void;
  onSkip: () => void;
}) {
  const [selectedCategories, setSelectedCategories] = useState<string[]>(initialPreferences.categories);
  const [budgetPreference, setBudgetPreference] = useState<"low" | "medium" | "high" | null>(
    initialPreferences.budget_preference,
  );
  const [selectedIntent, setSelectedIntent] = useState<string[]>(initialPreferences.intent);
  const [hasPets, setHasPets] = useState(initialPreferences.has_pets);
  const [hasKids, setHasKids] = useState(initialPreferences.has_kids);

  function toggleCategory(category: string) {
    setSelectedCategories((current) =>
      current.includes(category) ? current.filter((item) => item !== category) : [...current, category],
    );
  }

  function toggleIntent(intent: string) {
    setSelectedIntent((current) =>
      current.includes(intent) ? current.filter((item) => item !== intent) : [...current, intent],
    );
  }

  return (
    <div className="auth-shell">
      <div className="auth-card preferences-card preferences-card-wide">
        <div className="auth-header">
          <div className="auth-eyebrow">Personalized deals</div>
          <h1 className="auth-title">Help us tune your feed</h1>
          <p className="auth-copy">
            Pick a few interests and we’ll rank deals around what actually matters to you instead of showing a generic
            stream.
          </p>
        </div>

        <section className="preferences-section">
          <div className="preferences-section-title">Categories</div>
          <div className="preferences-grid">
            {PREFERENCE_OPTIONS.map((option) => {
              const isSelected = selectedCategories.includes(option);
              return (
                <button
                  key={option}
                  type="button"
                  className={isSelected ? "preference-chip preference-chip-active" : "preference-chip"}
                  onClick={() => toggleCategory(option)}
                >
                  {option}
                </button>
              );
            })}
          </div>
        </section>

        <section className="preferences-section">
          <div className="preferences-section-title">Budget preference</div>
          <div className="preferences-stack">
            {BUDGET_OPTIONS.map((option) => {
              const isSelected = budgetPreference === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  className={isSelected ? "preference-choice preference-choice-active" : "preference-choice"}
                  onClick={() => setBudgetPreference(option.value)}
                >
                  <strong>{option.label}</strong>
                  <span>{option.hint}</span>
                </button>
              );
            })}
          </div>
        </section>

        <section className="preferences-section">
          <div className="preferences-section-title">Intent</div>
          <div className="preferences-stack">
            {INTENT_OPTIONS.map((option) => {
              const isSelected = selectedIntent.includes(option.value);
              return (
                <button
                  key={option.value}
                  type="button"
                  className={isSelected ? "preference-choice preference-choice-active" : "preference-choice"}
                  onClick={() => toggleIntent(option.value)}
                >
                  <strong>{option.label}</strong>
                  <span>{option.hint}</span>
                </button>
              );
            })}
          </div>
        </section>

        <section className="preferences-section">
          <div className="preferences-section-title">Life context</div>
          <div className="preferences-grid preferences-grid-tight">
            <button
              type="button"
              className={hasPets ? "preference-chip preference-chip-active" : "preference-chip"}
              onClick={() => setHasPets((current) => !current)}
            >
              {hasPets ? "Pets ✓" : "Have pets"}
            </button>
            <button
              type="button"
              className={hasKids ? "preference-chip preference-chip-active" : "preference-chip"}
              onClick={() => setHasKids((current) => !current)}
            >
              {hasKids ? "Kids ✓" : "Have kids"}
            </button>
          </div>
        </section>

        {error ? <div className="auth-error">{error}</div> : null}

        <div className="preferences-actions">
          <button type="button" className="secondary-button" onClick={onSkip}>
            Use default feed
          </button>
          <button
            type="button"
            className="auth-submit"
            disabled={isSaving}
            onClick={() =>
              onSave({
                categories: selectedCategories,
                budget_preference: budgetPreference,
                intent: selectedIntent,
                has_pets: hasPets,
                has_kids: hasKids,
              })
            }
          >
            {isSaving ? "Saving..." : "Personalize my feed"}
          </button>
        </div>
      </div>
    </div>
  );
}
