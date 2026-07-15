"""Deterministic, local Smart Vertical Layout pipeline.

Heavy native vision modules are deliberately imported by the worker only when a smart
vertical job needs them. Horizontal jobs and API startup do not initialize OpenCV.
"""
