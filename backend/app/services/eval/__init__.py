"""Offline evaluation helpers for retrieval quality.

The modules in this package are deliberately dependency-light: every metric is
a pure function over plain sequences so it can be unit tested without a
database, Chroma, or an embedding provider.
"""
