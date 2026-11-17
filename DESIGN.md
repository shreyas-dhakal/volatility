---
name: Galvanise
description: "Neutral Astryx architecture workspace with evidence-led review."
colors:
  color-accent: "light-dark(#1b1b1b, #f1f1f1)"
  color-on-accent: "light-dark(#ffffff, #111111)"
  color-accent-muted: "light-dark(#d4d4d4, #474747)"
  color-background-body: "light-dark(#f1f1f1, #1b1b1b)"
  color-background-surface: "light-dark(#ffffff, #262626)"
  color-background-card: "light-dark(#ffffff, #1b1b1b)"
  color-neutral: "light-dark(#0000000F, #ffffff1A)"
  color-text-primary: "light-dark(#000000, #ffffff)"
  color-text-secondary: "light-dark(#474747, #9e9e9e)"
  color-text-disabled: "light-dark(#919191, #525252)"
  color-border: "light-dark(#00000014, #ffffff1A)"
  color-border-emphasized: "light-dark(#d4d4d4, #525252)"
  color-overlay-hover: "light-dark(#0000000D, #ffffff0D)"
  color-overlay-pressed: "light-dark(#0000001A, #ffffff1A)"
  color-background-purple: "light-dark(#f7d5ff, #4a2f51)"
  color-border-purple: "light-dark(#f3bfff, #d885eb)"
  color-background-orange: "light-dark(#ffc7a1, #503424)"
  color-border-orange: "light-dark(#ffc7a1, #df843f)"
  color-background-blue: "light-dark(#b9d7ff, #253c5a)"
  color-icon-blue: "light-dark(#003978, #88bcff)"
  color-icon-purple: "light-dark(#5c0e6c, #e496f6)"
  color-icon-orange: "light-dark(#622700, #ff9e55)"
  color-icon-teal: "light-dark(#00463d, #81c9bb)"
  color-icon-gray: "light-dark(#474747, #9e9e9e)"
  color-icon-disabled: "light-dark(#919191, #525252)"
  color-text-success: "light-dark(#2f7d33, #90ca90)"
  color-text-warning: "light-dark(#836700, #eec448)"
  color-text-error: "light-dark(#c0262c, #ffaea7)"
typography:
  headline:
    fontFamily: "Figtree, -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.3333
  title:
    fontFamily: "Figtree, -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.4
  section:
    fontFamily: "Figtree, -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 700
    lineHeight: 1.4118
  body:
    fontFamily: "Figtree, -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.4286
  label:
    fontFamily: "Figtree, -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
    lineHeight: 1.4286
  supporting:
    fontFamily: "Figtree, -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.6667
  code:
    fontFamily: 'ui-monospace, "SF Mono", Monaco, Consolas, "Liberation Mono", "Courier New", monospace'
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.4286
rounded:
  inner: "0.375rem"
  element: "0.625rem"
  container: "0.75rem"
spacing:
  "0": "0rem"
  "1": "0.25rem"
  "2": "0.5rem"
  "3": "0.75rem"
  "4": "1rem"
  "5": "1.25rem"
  "6": "1.5rem"
  "8": "2rem"
  "10": "2.5rem"
components:
  button-primary:
    backgroundColor: "{colors.color-accent}"
    textColor: "{colors.color-on-accent}"
    typography: "{typography.label}"
    rounded: "{rounded.element}"
    padding: "0.5rem 0.75rem"
    height: "32px"
  button-secondary:
    backgroundColor: "{colors.color-neutral}"
    textColor: "{colors.color-text-primary}"
    typography: "{typography.label}"
    rounded: "{rounded.element}"
    padding: "0.5rem 0.75rem"
    height: "32px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.color-text-primary}"
    typography: "{typography.label}"
    rounded: "{rounded.element}"
    padding: "0.5rem 0.75rem"
    height: "32px"
  text-field:
    backgroundColor: "{colors.color-background-surface}"
    textColor: "{colors.color-text-primary}"
    typography: "{typography.body}"
    rounded: "{rounded.element}"
    padding: "0.25rem 0.5rem"
  card:
    backgroundColor: "{colors.color-background-card}"
    rounded: "{rounded.container}"
    padding: "1rem"
  graph-node:
    backgroundColor: "{colors.color-background-body}"
    textColor: "{colors.color-text-primary}"
    rounded: "{rounded.container}"
    width: "210px"
---

# Design System: Galvanise

## Overview

**Creative North Star: "The Architecture Working Notebook"**

Galvanise uses the incumbent Astryx neutral identity: restrained grayscale surfaces, Figtree typography and compact controls around a spacious working column. The interface feels like a working notebook for architecture decisions, with conversation, evidence and review taking priority over decoration.

The creative north star names the implemented character; it does not introduce a replacement brand. Color is used for navigation/action icons, review states and graph meaning. Labels, provenance, review states and edge styles keep claims distinguishable without implying measured certainty.

**Key Characteristics:**

- Neutral surfaces and dark primary actions.
- Spacious conversation, compact navigation and evidence rows.
- Explicit provenance, uncertainty and review actions.
- Colored icons and graph annotations reinforced by labels and line style.

This is a source-based implementation record, refreshed from `apps/web/components/workspace.tsx`, `workspace-ui.tsx`, `graph.tsx`, `lib/graph-view.ts`, `app/layout.tsx`, `components/ui.tsx`, `astryx-themes.js` and the installed Astryx neutral/core styles. No visual inspection is claimed by this document. The earlier directional file's intended transcript and inspector widths are superseded by the values in Layout. `PRODUCT.md` delegates design decisions and requires the neutral identity.

## Colors

Frontmatter values preserve the installed theme's canonical CSS `light-dark()` strings, including alpha. Both the root and Theme component force light mode; the dark branches are library support, not an exposed application feature. Sidecar tonal strips are synthesized OKLCH preview metadata, not additional application palette tokens. Token keys correspond directly to `--<key>` CSS custom properties, scoped by the Astryx Theme provider.

### Primary

The charcoal accent supplies primary button fill, focus indication and strong interaction emphasis; on-accent supplies its contrasting label. Accent-muted supports inset field focus. This is a neutral identity with no separate brand hue.

### Secondary

Small navigation/action icons use the installed blue, purple, orange and teal families: blue for Chat and Files & code, purple for Decisions and Designs, orange for Changes and Questions, teal for Code map. Settings uses gray. Review icons use semantic success, warning and error colors, resolved through the theme’s corresponding text-color aliases: green check for Approved, amber clock for Needs review, red X for Not used. Unavailable controls use disabled gray plus explanation; color is never the only state cue.

Graph annotations use the installed purple family for proposed boundary groups, orange for selected change-driver matches and blue for business-decision nodes. Purple boundaries also have dashed borders; orange matches have a heavier border and a textual match suffix. These roles must retain visible explanations.

### Neutral

Body is the pale navigation-rail background and ordinary graph-node fill. Surface is the white main working area and authentication/input surface; card is the white contained surface. Primary text carries content; secondary text carries explanation and provenance; disabled text is for unavailable controls. The translucent border divides regions and evidence rows; emphasized border outlines fields. Neutral fill marks secondary controls and current navigation; hover and pressed overlays communicate interaction.

**The Evidence Color Rule.** Graph color identifies a semantic category, never verification or a probability score. Retain labels and dashed versus solid edge treatment.

## Typography

**Heading and body font:** Figtree with the system fallback stack in frontmatter. The application self-hosts Figtree weights 400, 500, 600 and 700 through `@fontsource/figtree` imports in the root layout. Webpack suppresses the generated theme module's remote `fonts.css` import; keep that generated module unchanged. The fallback stack remains available while font assets load. **Code font:** the monospace stack in frontmatter, used by Markdown code and raw evidence.

Hierarchy is the installed neutral theme's compact operational scale, not a display/marketing scale. Headline maps to Heading level 1; title to level 2; section to level 3. Body serves conversation and descriptions; label serves controls and metadata headings; supporting serves status, helpers and provenance. Explicit semibold overrides mark speakers, objectives and data keys. No application display role is used. Frontmatter sizes are the nominal default values; Astryx's dynamic type scaling can change rendered size.

**The Reading Hierarchy Rule.** Use heading levels to structure tasks, body text for reasoning and supporting text for evidence qualifiers. Keep essential uncertainty legible rather than hiding it in color alone.

## Layout

The authenticated shell occupies the dynamic viewport height (`100dvh`) with nested flex regions. Main content and the rail scroll independently; the composer is a non-shrinking region below the transcript with a top divider. Flexible columns set minimum width and height to zero to permit shrinking.

- Desktop rail: fixed width (15.5rem / 248px), pale body fill, right divider, padding step 5 and major gaps step 6.
- Conversation: centered, full available width up to (48rem / 768px), content padding step 6, message gaps step 6. Project creation uses this same measure.
- Context inspector: width (20rem / 320px), left divider, padding step 5; rendered alongside Chat only when a project exists and project creation is closed.
- At widths at or below (1100px), the inspector is hidden. The header's Project notes action opens a separate main-column Project notes view with return-to-chat navigation.
- At widths at or below (760px), the rail becomes an absolute, full-frame navigation region controlled by Menu and Close menu. It is not implemented as a modal dialog: no bespoke focus trap, backdrop or inert treatment is established.
- Header and action/filter rows wrap where declared. Menu and Close menu are hidden above the navigation breakpoint. Menu and composer Send/Stop actions do not shrink; the project title can ellipsize and composer helper text can wrap, preserving the action labels at narrow widths. Small spacing steps 1-3 group labels and actions; steps 4-6 separate controls and sections; step 8 supports onboarding empty states. The system uses Astryx's quarter-rem spacing rhythm.
- Authentication is centered on a surface background, with a card and inner content capped at (29rem / 464px). Empty workspace/conversation regions have minimum height (22rem).
- Graph canvas: height (38rem), minimum height (24rem), clipped rounded boundary. Introductory explanation is capped at (70ch). Graph navigation uses pan/zoom, controls and minimap rather than shrinking every node into a narrow viewport.

These dimensions describe source behavior, not proof that every narrow-screen state has been visually verified. Long data, dense graph labels and narrow action rows still require rendered checks.

## Elevation & Depth

The application is flat by default: tonal body/surface separation, thin dividers, rounded boundaries and selected fills supply hierarchy. The authentication Card uses Astryx's default `elevation="none"`. Application layout adds no custom drop shadow. Library overlays and React Flow controls can use their own library treatments; those are not a new Galvanise elevation vocabulary. Inputs use inset hover/focus rings; buttons inherit the shared keyboard outline.

**The Flat Workspace Rule.** Organize persistent working regions with semantic fills and dividers; reserve library elevation for transient controls that require it.

## Shapes

Soft rectangular controls use the neutral theme's element radius; cards, notices, graph nodes and canvas use container radius. The smaller inner radius is available for nested/small controls. Small Astryx buttons reduce their corner radius by one spacing step. Borders are thin and neutral; graph boundary groups use dashed outlines and change-driver matches use a heavier outline. No bespoke pill/chip pattern is implemented in the workspace.

## Components

### Buttons

Use Astryx Button directly. Primary is the charcoal high-emphasis action (sign in, create project, send, create design options); the default secondary variant is the soft neutral action; ghost serves navigation, dismissal and supporting actions. Default medium height is (32px), small is (28px), and actual height can expand to fit line height. The common internal inset is vertical step 2, horizontal step 3. Labels are brief, plain sentence case, such as Send, Edit, Files & code and Code map. Buttons remain actual Astryx Button controls; do not replace them with custom button primitives. Keep the library loading, disabled, hover overlay, pressed feedback and focus-visible behavior. Buttons transition with the installed fast duration (125ms) and standard easing; reduced-motion disables the library transition and press scaling.

### Inputs / Fields

TextInput, TextArea, Selector and FileInput are supported Astryx controls. Fields use surface fill, emphasized border and element corners. The common field wrapper uses vertical step 1 and horizontal step 2; focus changes border to accent and adds an accent-muted inset ring. Preserve visible labels and descriptions; the composer hides its label visually while retaining its accessible name. Forms use required fields and appropriate autocomplete. Loading/disabled state is passed through the library API. Authentication failures and server errors surface through the application's shared error notice rather than a complete bespoke inline-validation system.

### Navigation

The rail uses left-aligned, full-width Astryx Button entries with small colored icons: secondary fill for the active view, ghost for the rest. Main labels are Chat, Files & code, Decisions, Changes, Questions, Designs and Code map; Settings is separated toward the bottom. Project selection, new-project action, conversation history and source summaries share the rail. Selected conversation also uses secondary fill. Menu and Close menu appear only at widths at or below (760px). Semantic nav/aside labels are present and active navigation uses `aria-current="page"`. Project-dependent navigation is disabled before a project is created, with a Create a project first explanation.

### Icons and review states

`AppIcon` wraps the supported Astryx Icon with `size="sm"`, semantic colors and Lucide SVG components; it does not implement a competing icon or button system. Primary-action icons inherit the button's contrasting label color. ReviewState pairs an icon with explicit Approved, Not used or Needs review text. Connected GitHub uses a green check; unavailable GitHub shows a disabled gray action labelled GitHub not set up and explains that files can be uploaded now. Refresh is icon-only with an accessible label and tooltip. Preserve text labels on other task actions.

### Cards / Containers

The authentication card uses the default bordered Astryx Card with no elevation and default padding step 4; its inner stack supplies the larger content rhythm. Most workspace content is unboxed. Evidence records and architecture candidates use rows with bottom dividers, vertical padding step 5, headings and compact supporting metadata. Context sections use stacked summaries rather than separate floating cards.

### Conversation and feedback

Messages use a speaker label followed by Markdown, with no decorative speech-bubble palette. The composer is persistent beneath the scrolling transcript and switches Send to Stop while streaming. Stream updates use a polite live region; interrupted responses retain a partial-response label. Error notices use a container-radius surface, border, step-4 inset and `role="alert"`, with a red warning icon, the heading Something needs attention, actionable server text and a separate Dismiss action. There is no toast system in this implementation. Transcript scrolling requests smooth motion directly; a custom reduced-motion guard for that behavior has not been established.

### Evidence review and design comparison

Knowledge rows show a finding title, a labelled review state, a readable evidence qualifier and description. Common evidence labels are Checked against a source, Confirmed by a person, AI suggestion and Source not confirmed. Approve, Leave out, Edit and Sources & history remain adjacent; decisions can Find related code. Editing reveals Title and Description fields; questions add answer entry. Details and previous versions use readable labelled fields instead of raw JSON. Field labels translate implementation names into Purpose, What stays the same, Sources, How we know, Things to consider and What to check next. Scalar statuses and booleans are rendered in plain language; unknown metadata names can still fall back to humanized field names.

Design options describe proposed parts, reasons and Things to confirm alongside review/history controls. Try a change asks What might change? and lets the user select where the change starts. Current system and Proposed design results wrap side by side where space allows. Results explain when code information is insufficient and say that the comparison is a guide rather than a prediction. Keep implementation terminology out of task labels and copy; technical identifiers may still appear where they are actual source evidence.

### Architecture graph

The graph is a dedicated working view, not the landing state. It supports graph, driver and candidate selection, name/path search, a Show nearby code selector, part/source inspection and From/To selectors for finding a connection. Users choose named code parts instead of typing node IDs. The current request limit is 80 nodes; the UI reports returned part and connection counts. Standard nodes are (210px) wide with minimum height (65px), non-draggable and selectable/focusable. Proposed groups use a dashed rounded purple container and have textual contracts below the canvas. Nodes expose accessible labels and selection instructions. Solid edges mean explicitly verified or human-confirmed evidence; other edges use a (6 4) dash pattern and concise inferred/source labels; accessible edge labels retain the fuller unverified qualification. Arrowheads indicate direction. Upstream confidence is retained in accessible edge labels as upstream confidence, not Galvanise verification. The visible legend says Dashed connections need checking. Connection paths render as readable names joined by arrows, with a plain empty-result message. Graph edge labels currently use small (10px) text, so retain the larger explanatory legend and inspectable detail. Do not claim complete canvas accessibility solely from keyboard node selection.

### Supported entry and source flows

The interface includes sign-in, registration, GitHub continuation, project creation, new/existing system choice and a deliberately labelled synthetic sample project. Files & code accepts TXT, Markdown, PDF and DOCX documents; Graphify JSON import; and read-only public GitHub repositories. Import activity lists real job states/errors. Repository indexing creates file nodes; imported graph relationships provide dependency exploration. AI and GitHub availability are reported from server configuration, and unavailable AI is explained in the empty chat state and Settings. Send and Create design options are disabled when AI is unavailable, with setup explanations. GitHubAction suppresses the OAuth link when GitHub is not configured and explains the unavailable control. Connected accounts show their real connection state. These are implemented controls and flows, not assertions that external integrations are configured in every environment.

## Do's and Don'ts

### Do:

- Do use the supported Astryx components and semantic CSS properties.
- Do show readable evidence and review labels beside findings, with source details and previous versions available on demand.
- Do provide labelled controls and a reachable composer at narrow widths.
- Do preserve source confidence as an upstream claim and identify synthetic sample evidence.

### Don't:

- Don't introduce a new brand accent or decorative chart palette.
- Don't expose raw JSON, manual node IDs or internal field names as the normal review workflow.
- Don't imply that repository file indexing establishes dependency relationships.
- Don't present qualitative scenario assumptions as measured savings or verified impact.
- Don't claim dark-mode, mobile-drawer modality or reduced-motion coverage beyond the implementation.
