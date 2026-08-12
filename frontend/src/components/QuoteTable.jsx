import { useMemo, useState } from 'react';

import './QuoteTable.css';

const money = (value) =>
  typeof value === 'number'
    ? new Intl.NumberFormat('en-CA', {
        style: 'currency',
        currency: 'CAD',
        maximumFractionDigits: 0,
      }).format(value)
    : null;

const SORTS = {
  price: (a, b) => {
    // Unavailable sources always sink to the bottom, never sorted among prices.
    if (a.annual_premium == null) return b.annual_premium == null ? 0 : 1;
    if (b.annual_premium == null) return -1;
    return a.annual_premium - b.annual_premium;
  },
  name: (a, b) => a.channel_name.localeCompare(b.channel_name),
};

export default function QuoteTable({ summary, quotes, apiBase, onBack }) {
  const [sort, setSort] = useState('price');
  const [proof, setProof] = useState(null);

  const rows = useMemo(() => [...quotes].sort(SORTS[sort]), [quotes, sort]);
  const priced = quotes.filter((q) => typeof q.annual_premium === 'number');
  const average = summary?.average_annual;

  return (
    <div className="qt">
      <header className="qt__head">
        <div>
          <h2>All sources compared</h2>
          <p>
            {summary?.channels_with_a_price ?? priced.length} of{' '}
            {summary?.channels_run ?? quotes.length} sources returned a rate
            {average ? ` · average ${money(average)}/yr` : ''}
          </p>
        </div>
        <div className="qt__head-actions">
          <label className="qt__sort">
            Sort
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="price">Cheapest first</option>
              <option value="name">Source name</option>
            </select>
          </label>
          <button type="button" className="qt__back" onClick={onBack}>
            Back to cards
          </button>
        </div>
      </header>

      <div className="qt__scroll">
        <table className="qt__table">
          <thead>
            <tr>
              <th scope="col">Source</th>
              <th scope="col">Type</th>
              <th scope="col" className="qt__num">
                Per year
              </th>
              <th scope="col" className="qt__num">
                Per month
              </th>
              <th scope="col">Matched on</th>
              <th scope="col">Proof</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((q) => {
              const unavailable = q.annual_premium == null;
              const monthly = unavailable ? null : Math.round(q.annual_premium / 12);
              const delta =
                !unavailable && average ? Math.round(q.annual_premium - average) : null;

              return (
                <tr
                  key={q.channel_id}
                  className={`${q.is_recommended ? 'is-best' : ''} ${
                    unavailable ? 'is-unavailable' : ''
                  }`}
                >
                  <th scope="row">
                    <span className="qt__name">{q.channel_name}</span>
                    {q.is_recommended && <span className="qt__badge">Best rate</span>}
                  </th>
                  <td className="qt__cat">{q.channel_category}</td>
                  <td className="qt__num qt__price">
                    {unavailable ? (
                      <span className="qt__null">Unavailable</span>
                    ) : (
                      <>
                        {money(q.annual_premium)}
                        {delta !== null && delta !== 0 && (
                          <em className={delta < 0 ? 'is-under' : 'is-over'}>
                            {delta < 0 ? '−' : '+'}
                            {money(Math.abs(delta))}
                          </em>
                        )}
                      </>
                    )}
                  </td>
                  <td className="qt__num">{unavailable ? '—' : money(monthly)}</td>
                  <td className="qt__matched">
                    {unavailable ? (
                      <span title={q.headline || ''}>
                        {q.unavailable_reason || 'no rate returned'}
                      </span>
                    ) : (
                      q.matched_on || '—'
                    )}
                  </td>
                  <td>
                    {q.screenshot_url ? (
                      <button
                        type="button"
                        className="qt__proof"
                        onClick={() => setProof(q)}
                        aria-label={`Screenshot proof from ${q.channel_name}`}
                      >
                        View
                      </button>
                    ) : (
                      <span className="qt__null">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="qt__foot">
        Benchmarks and published averages, not binding quotes. Every figure links to a
        screenshot of the page it was read from.
      </p>

      {proof && (
        <div
          className="qt__lightbox"
          role="dialog"
          aria-label={`${proof.channel_name} screenshot`}
          onClick={() => setProof(null)}
        >
          <figure onClick={(e) => e.stopPropagation()}>
            <figcaption>
              <strong>{proof.channel_name}</strong>
              {proof.annual_premium != null && <span>{money(proof.annual_premium)}/yr</span>}
              <button type="button" onClick={() => setProof(null)} aria-label="Close">
                ✕
              </button>
            </figcaption>
            <img src={`${apiBase}${proof.screenshot_url}`} alt={`${proof.channel_name} source page`} />
            {proof.source_url && (
              <a href={proof.source_url} target="_blank" rel="noreferrer noopener">
                Open the live page
              </a>
            )}
          </figure>
        </div>
      )}
    </div>
  );
}
