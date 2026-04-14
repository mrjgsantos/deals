const CATEGORY_ICONS: Record<string, string> = {
  Electronics: "⚡",
  Tech: "💻",
  Home: "🏠",
  Sports: "🏃",
  Beauty: "✨",
  Health: "💊",
  Kitchen: "🍳",
  Fashion: "👗",
  Books: "📚",
  Toys: "🎮",
  Garden: "🌱",
  Office: "📋",
  Lifestyle: "🌟",
  Food: "🛒",
  Automotive: "🚗",
  Baby: "🍼",
  Pets: "🐾",
  Travel: "✈️",
  Music: "🎵",
  Tools: "🔧",
};

export function CategoryScroller({
  categories,
  selected,
  onSelect,
}: {
  categories: string[];
  selected: string | null;
  onSelect: (category: string | null) => void;
}) {
  if (categories.length < 2) return null;

  return (
    <div className="d-category-scroller" role="navigation" aria-label="Filter by category">
      <div className="d-category-track">
        <button
          type="button"
          className={`d-category-pill${selected === null ? " d-category-pill-active" : ""}`}
          onClick={() => onSelect(null)}
        >
          All deals
        </button>
        {categories.map((cat) => (
          <button
            key={cat}
            type="button"
            className={`d-category-pill${selected === cat ? " d-category-pill-active" : ""}`}
            onClick={() => onSelect(cat)}
          >
            {CATEGORY_ICONS[cat] ?? "🏷"} {cat}
          </button>
        ))}
      </div>
    </div>
  );
}
