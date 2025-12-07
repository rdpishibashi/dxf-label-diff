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


def group_labels_by_coordinate(rounded_labels):
    """
    Group rounded label tuples by coordinate and count label occurrences.

    Args:
        rounded_labels: List of (label, rounded_x, rounded_y) tuples

    Returns:
        dict: {(x, y): Counter({label: count, ...}), ...}
    """
    coordinate_map = {}
    for label, x, y in rounded_labels:
        coord = (x, y)
        if coord not in coordinate_map:
            coordinate_map[coord] = Counter()
        coordinate_map[coord][label] += 1
    return coordinate_map


def append_unmatched_pairs(change_pairs, coord, labels, source):
    """Append rows for labels that exist only in one file."""
    for label, count in sorted(labels.items()):
        for _ in range(count):
            change_pairs.append({
                'coordinate': coord,
                'label_a': label if source == 'A' else None,
                'label_b': label if source == 'B' else None,
            })


def find_label_change_pairs(group_a, group_b):
    """
    Identify label change candidates by comparing counters at each coordinate.

    Args:
        group_a: dict from group_labels_by_coordinate for file A
        group_b: dict from group_labels_by_coordinate for file B

    Returns:
        list: List of dicts with keys:
            - 'coordinate': (x, y)
            - 'label_a': label text in file A
            - 'label_b': label text in file B
    """
    change_pairs = []
    all_coords = sorted(set(group_a.keys()) | set(group_b.keys()))

    for coord in all_coords:
        counter_a = group_a.get(coord)
        counter_b = group_b.get(coord)

        if counter_a is None and counter_b is None:
            continue

        if counter_a is None:
            append_unmatched_pairs(change_pairs, coord, counter_b, 'B')
            continue

        if counter_b is None:
            append_unmatched_pairs(change_pairs, coord, counter_a, 'A')
            continue

        # Remove identical labels that remain unchanged
        remaining_a = counter_a.copy()
        remaining_b = counter_b.copy()

        shared_labels = set(remaining_a.keys()) & set(remaining_b.keys())
        for label in shared_labels:
            min_count = min(remaining_a[label], remaining_b[label])
            remaining_a[label] -= min_count
            remaining_b[label] -= min_count
            if remaining_a[label] == 0:
                del remaining_a[label]
            if remaining_b[label] == 0:
                del remaining_b[label]

        if not remaining_a or not remaining_b:
            continue

        # Pair leftover labels (potential renames) in deterministic order
        labels_a = sorted(list(remaining_a.elements()))
        labels_b = sorted(list(remaining_b.elements()))
        max_pairs = min(len(labels_a), len(labels_b))

        for idx in range(max_pairs):
            change_pairs.append({
                'coordinate': coord,
                'label_a': labels_a[idx],
                'label_b': labels_b[idx],
            })

        # Add unmatched labels from A
        for idx in range(max_pairs, len(labels_a)):
            change_pairs.append({
                'coordinate': coord,
                'label_a': labels_a[idx],
                'label_b': None,
            })

        # Add unmatched labels from B
        for idx in range(max_pairs, len(labels_b)):
            change_pairs.append({
                'coordinate': coord,
                'label_a': None,
                'label_b': labels_b[idx],
            })

    return change_pairs


def build_label_change_rows(change_pairs):
    """
    Convert change pairs into rows for Excel export.

    Args:
        change_pairs: Output from find_label_change_pairs

    Returns:
        list: List of dict rows with coordinate and transition info
    """
    rows = []
    for pair in change_pairs:
        coord_x, coord_y = pair['coordinate']
        rows.append({
            'Coordinate X': coord_x,
            'Coordinate Y': coord_y,
            'Label A': pair['label_a'] or "",
            'Label B': pair['label_b'] or "",
        })
    return rows
