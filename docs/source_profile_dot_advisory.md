## NYC DOT Traffic Advisory Profile

### Source Inventory

The NYC DOT Traffic Advisory was evaluated as a potential bonus source for traffic closure and event information.

| Source | URL | Format | Coverage | Structure | Status | Evidence |
|---|---|---|---|---|---|---|
| Weekly Traffic Advisory | https://www.nyc.gov/html/dot/html/motorist/weektraf.shtml | HTML | Saturday–Friday advisory period | Semi-structured HTML | Profiled | 2026-09-14 HTML snapshot |
| Weekend Traffic Advisory | https://www.nyc.gov/html/dot/html/motorist/wkndtraf.shtml | HTML | Friday–Sunday advisory period | Semi-structured HTML | Profiled | 2026-09-14 HTML snapshot |

The live NYC DOT advisory pages provide information about temporary closures affecting streets, bridges, highways, and tunnels due to construction, special events, parades, and other permitted activities.

### API / Download Alternative Check

NYC DOT provides transportation data through its data feeds and NYC Open Data.

Historical NYC Open Data entries were identified for:

- Weekend Traffic Updates
- Special Traffic Updates

These entries were last updated in **October 2024** and point to NYC DOT traffic advisory pages rather than providing a current machine-readable equivalent of the live 2026 advisory.

No suitable current machine-readable API or downloadable structured equivalent was identified during the feasibility check.

**Result:** HTML scraping is considered a reasonable fallback if the source is implemented.

### HTML Structure Assessment

#### Weekly Traffic Advisory

The Weekly Advisory is organized into geographic sections such as:

- East River Bridge Crossings
- Manhattan
- Bronx
- Brooklyn
- Queens
- Cross-borough sections

Individual advisories do not follow one consistent HTML structure.

Observed patterns include:

```html
<h3>Location</h3>
<p>Description</p>
```

and:

```html
<strong>Location</strong>
<p>Description</p>
```

Event sections use additional elements for:

- Event name
- Location(s)
- Formation
- Route
- Dispersal

#### Weekend Traffic Advisory

The Weekend Advisory is organized into geographic sections including:

- Bronx
- Brooklyn
- Manhattan
- Manhattan/Brooklyn
- Queens
- Queens/Brooklyn
- Staten Island
- Citywide

Many ordinary traffic advisories use a recognizable structure:

```html
<strong>Location</strong>
<p>Description</p>
```

Events use a different structure containing:

- Event name
- Location(s)
- Formation
- Route
- Dispersal

### Structure Finding

The HTML is sufficiently identifiable for targeted extraction, but it is **semi-structured rather than fully standardized**.

A future scraper should not depend on a single HTML tag or CSS selector because valid advisories already appear in multiple formats.

For example, relying only on `<h3>` would miss advisories represented using `<strong>`.

### Data Identifiability

Potential fields identifiable from the Weekend Traffic Advisory include:

| Field | Identifiability | Notes |
|---|---|---|
| Advisory period | Yes | Identified from page heading |
| Geographic area / borough | Yes | Identified from geographic sections |
| Location | Yes | Street, bridge, highway, or affected location |
| Description | Yes | Natural-language advisory text |
| Closure date | Yes | Often embedded in description |
| Closure time | Yes | Often embedded in description |
| Direction | Often | Depends on advisory |
| Closure type | Often | Depends on advisory |
| Reason / project | Often | Depends on advisory |
| Event name | Yes | For event records |
| Event location(s) | Yes | For event records |
| Formation | Sometimes | Event-specific |
| Route | Sometimes | Event-specific |
| Dispersal | Sometimes | Event-specific |
| Source URL | Yes | Source metadata |
| Retrieval timestamp | Yes | Ingestion metadata |

Dates and times are frequently embedded in natural-language descriptions. Normalizing them into structured datetime fields would therefore require additional parsing logic.

### Duplicate and Overlap Considerations

The Weekly and Weekend advisories have overlapping coverage.

The Weekly Advisory covers Saturday through Friday, while the Weekend Advisory covers Friday through Sunday. Implementing both sources could therefore produce overlapping advisories and would require duplicate or overlap handling.

For the bonus implementation, the Weekend Traffic Advisory is recommended as the narrower source.

### Anomalies and Maintenance Risks

Potential failure points include:

- HTML tags or selectors changing
- Geographic section IDs changing
- New advisory formats being introduced
- Event sections changing structure
- Date/time wording changing
- Content being moved to another page component or template

A scraper relying on a single selector could silently miss valid advisories.

### Feasibility Assessment

| Criteria | Assessment |
|---|---|
| Official/public source | Pass |
| Current information | Pass |
| Geographic sections identifiable | Pass |
| Individual advisories identifiable | Pass with multiple patterns |
| Consistent HTML structure | Partial |
| Data richness | High |
| Parsing complexity | Medium–High |
| Maintenance risk | Medium–High |
| Current machine-readable alternative | Not identified |
| Overall feasibility | Feasible |

### Recommendation

**BUILD — NYC DOT Weekend Traffic Advisory**

The Weekend Traffic Advisory is recommended as the bonus source because it provides useful traffic closure and event information while having a narrower scope than the Weekly Advisory.

The source is feasible to scrape, but its semi-structured HTML creates medium-to-high maintenance risk.

If implemented, the ingestion process should preserve:

- Raw HTML snapshot
- Source URL
- Retrieval timestamp
- Raw advisory text

Preserving the raw source will allow parsing logic to be updated later without losing the original advisory data.

No scraper is implemented as part of this profiling issue.
