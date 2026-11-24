---
version: 1.0.0
name: Symaira AppKit Design System
description: Native Symaira component, material, accessibility and release handoff for the shared Swift package.
---

## Overview

Document reusable native foundations; never move product-specific behavior into AppKit.

## Colors

Warm black, champagne and product accents follow the shared Symaira semantic roles.

## Typography

Use native Dynamic Type/system typography in clients and readable system fallbacks in OpenDesign fixtures.

## Material hierarchy

Canvas, content surfaces, interactive chrome and feedback remain distinct. Native Liquid Glass is limited to supported system controls; ordinary content uses standard material or opaque accessibility fallback.

## Components

Cover buttons, badges, notices, empty/loading states, tool discovery, Keychain boundaries and update status.

## Accessibility

VoiceOver labels, keyboard focus, reduced transparency/motion, increased contrast and touch targets are mandatory.

## Brand and distribution

Keep product glyphs owned by products; shared shell, safe zones, deterministic renderers and DMG layout live here.

## Anti-patterns

No app-specific views, no hand-rolled duplicate themes, no cloud/SaaS code and no release-time sibling checkout dependency.
