"""
Coordinate-based label comparison utilities

This module provides functions for comparing labels with coordinate information,
including coordinate rounding and aggregation by label name.
"""

from collections import Counter


def round_coordinate(value, tolerance):
    """
    Round coordinate value based on tolerance

    Args:
        value: Coordinate value (float)
        tolerance: Tolerance for rounding (e.g., 0.01)

    Returns:
        float: Rounded coordinate value

    Example:
        >>> round_coordinate(100.456, 0.01)
        100.46
        >>> round_coordinate(100.456, 0.1)
        100.5
    """
    return round(value / tolerance) * tolerance


def round_labels_with_coordinates(labels, tolerance):
    """
    Round all coordinates in label tuples

    Args:
        labels: List of (label, x, y) tuples
        tolerance: Tolerance for coordinate rounding

    Returns:
        list: List of (label, rounded_x, rounded_y) tuples
    """
    rounded_labels = []
    for label, x, y in labels:
        rounded_x = round_coordinate(x, tolerance)
        rounded_y = round_coordinate(y, tolerance)
        rounded_labels.append((label, rounded_x, rounded_y))
    return rounded_labels


def aggregate_by_label(counter_a, counter_b):
    """
    Aggregate coordinate-based comparison by label name

    This function takes two Counters of (label, x, y) tuples and aggregates
    them by label name, splitting into A only, B only, and Common categories.

    Args:
        counter_a: Counter of (label, x, y) tuples from file A
        counter_b: Counter of (label, x, y) tuples from file B

    Returns:
        dict: Dictionary with label names as keys and dict with:
            - 'a_only': count of items only in A
            - 'b_only': count of items only in B
            - 'common': count of items in both

    Example:
        >>> counter_a = Counter([('R10', 100, 200), ('R10', 150, 250)])
        >>> counter_b = Counter([('R10', 100, 200), ('R20', 300, 400)])
        >>> result = aggregate_by_label(counter_a, counter_b)
        >>> result['R10']
        {'a_only': 1, 'b_only': 0, 'common': 1}
    """
    # Calculate set differences
    set_a = set(counter_a.keys())
    set_b = set(counter_b.keys())

    a_only_tuples = set_a - set_b
    b_only_tuples = set_b - set_a
    common_tuples = set_a & set_b

    # Aggregate by label name
    label_summary = {}

    # Process A only items
    for label_tuple in a_only_tuples:
        label = label_tuple[0]
        count = counter_a[label_tuple]
        if label not in label_summary:
            label_summary[label] = {'a_only': 0, 'b_only': 0, 'common': 0}
        label_summary[label]['a_only'] += count

    # Process B only items
    for label_tuple in b_only_tuples:
        label = label_tuple[0]
        count = counter_b[label_tuple]
        if label not in label_summary:
            label_summary[label] = {'a_only': 0, 'b_only': 0, 'common': 0}
        label_summary[label]['b_only'] += count

    # Process common items
    for label_tuple in common_tuples:
        label = label_tuple[0]
        count_a = counter_a[label_tuple]
        count_b = counter_b[label_tuple]
        if label not in label_summary:
            label_summary[label] = {'a_only': 0, 'b_only': 0, 'common': 0}

        # Count common items as minimum of both
        common_count = min(count_a, count_b)
        label_summary[label]['common'] += common_count

        # Add differences to a_only or b_only
        if count_a > count_b:
            label_summary[label]['a_only'] += (count_a - count_b)
        elif count_b > count_a:
            label_summary[label]['b_only'] += (count_b - count_a)

    return label_summary


def create_data_rows_from_summary(label_summary):
    """
    Create data rows for Excel output from label summary

    Args:
        label_summary: Dictionary from aggregate_by_label()

    Returns:
        list: List of dictionaries for DataFrame creation
            Each dict has keys: 'label', 'a_only', 'b_only', 'common'
    """
    data_rows = []

    for label in sorted(label_summary.keys()):
        summary = label_summary[label]

        # Add A only row if exists
        if summary['a_only'] > 0:
            data_rows.append({
                'label': label,
                'count_a': summary['a_only'],
                'count_b': 0,
                'status': 'A Only',
                'diff': -summary['a_only']
            })

        # Add B only row if exists
        if summary['b_only'] > 0:
            data_rows.append({
                'label': label,
                'count_a': 0,
                'count_b': summary['b_only'],
                'status': 'B Only',
                'diff': summary['b_only']
            })

        # Add Common row if exists
        if summary['common'] > 0:
            data_rows.append({
                'label': label,
                'count_a': summary['common'],
                'count_b': summary['common'],
                'status': 'Same',
                'diff': 0
            })

    return data_rows
