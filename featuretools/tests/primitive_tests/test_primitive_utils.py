import os

import numpy as np
import pandas as pd
import pytest

from featuretools import list_primitives
from featuretools.primitives import (
    Age,
    Count,
    Day,
    GreaterThan,
    Haversine,
    Last,
    Max,
    Mean,
    Min,
    Mode,
    Month,
    NumCharacters,
    NumUnique,
    NumWords,
    PercentTrue,
    Skew,
    Std,
    Sum,
    Weekday,
    Year,
    get_aggregation_primitives,
    get_default_aggregation_primitives,
    get_default_transform_primitives,
    get_transform_primitives
)
from featuretools.primitives.base import PrimitiveBase
from featuretools.primitives.utils import (
    _get_descriptions,
    _get_unique_input_types,
    _roll_series_with_gap,
    list_primitive_files,
    load_primitive_from_file
)
from featuretools.utils.gen_utils import Library


def test_list_primitives_order():
    df = list_primitives()
    all_primitives = get_transform_primitives()
    all_primitives.update(get_aggregation_primitives())

    for name, primitive in all_primitives.items():
        assert name in df['name'].values
        row = df.loc[df['name'] == name].iloc[0]
        actual_desc = _get_descriptions([primitive])[0]
        if actual_desc:
            assert actual_desc == row['description']
        assert row['dask_compatible'] == (Library.DASK in primitive.compatibility)
        assert row['valid_inputs'] == ', '.join(_get_unique_input_types(primitive.input_types))
        assert row['return_type'] == getattr(primitive.return_type, '__name__', None)

    types = df['type'].values
    assert 'aggregation' in types
    assert 'transform' in types


def test_valid_input_types():
    actual = _get_unique_input_types(Haversine.input_types)
    assert actual == {'<ColumnSchema (Logical Type = LatLong)>'}
    actual = _get_unique_input_types(GreaterThan.input_types)
    assert actual == {'<ColumnSchema (Logical Type = Datetime)>',
                      "<ColumnSchema (Semantic Tags = ['numeric'])>",
                      '<ColumnSchema (Logical Type = Ordinal)>'}
    actual = _get_unique_input_types(Sum.input_types)
    assert actual == {"<ColumnSchema (Semantic Tags = ['numeric'])>"}


def test_descriptions():
    primitives = {NumCharacters: 'Calculates the number of characters in a string.',
                  Day: 'Determines the day of the month from a datetime.',
                  Last: 'Determines the last value in a list.',
                  GreaterThan: 'Determines if values in one list are greater than another list.'}
    assert _get_descriptions(list(primitives.keys())) == list(primitives.values())


def test_get_default_aggregation_primitives():
    primitives = get_default_aggregation_primitives()
    expected_primitives = [Sum, Std, Max, Skew, Min, Mean, Count, PercentTrue,
                           NumUnique, Mode]
    assert set(primitives) == set(expected_primitives)


def test_get_default_transform_primitives():
    primitives = get_default_transform_primitives()
    expected_primitives = [Age, Day, Year, Month, Weekday, Haversine, NumWords,
                           NumCharacters]
    assert set(primitives) == set(expected_primitives)


@pytest.fixture
def this_dir():
    return os.path.dirname(os.path.abspath(__file__))


@pytest.fixture
def primitives_to_install_dir(this_dir):
    return os.path.join(this_dir, "primitives_to_install")


@pytest.fixture
def bad_primitives_files_dir(this_dir):
    return os.path.join(this_dir, "bad_primitive_files")


def test_list_primitive_files(primitives_to_install_dir):
    files = list_primitive_files(primitives_to_install_dir)
    custom_max_file = os.path.join(primitives_to_install_dir, "custom_max.py")
    custom_mean_file = os.path.join(primitives_to_install_dir, "custom_mean.py")
    custom_sum_file = os.path.join(primitives_to_install_dir, "custom_sum.py")
    assert {custom_max_file, custom_mean_file, custom_sum_file}.issubset(set(files))


def test_load_primitive_from_file(primitives_to_install_dir):
    primitve_file = os.path.join(primitives_to_install_dir, "custom_max.py")
    primitive_name, primitive_obj = load_primitive_from_file(primitve_file)
    assert issubclass(primitive_obj, PrimitiveBase)


def test_errors_more_than_one_primitive_in_file(bad_primitives_files_dir):
    primitive_file = os.path.join(bad_primitives_files_dir, "multiple_primitives.py")
    error_text = "More than one primitive defined in file {}".format(primitive_file)
    with pytest.raises(RuntimeError) as excinfo:
        load_primitive_from_file(primitive_file)
    assert str(excinfo.value) == error_text


def test_errors_no_primitive_in_file(bad_primitives_files_dir):
    primitive_file = os.path.join(bad_primitives_files_dir, "no_primitives.py")
    error_text = "No primitive defined in file {}".format(primitive_file)
    with pytest.raises(RuntimeError) as excinfo:
        load_primitive_from_file(primitive_file)
    assert str(excinfo.value) == error_text


def get_number_of_days(offset):
    if isinstance(offset, str):
        return int(offset[0])
    else:
        return offset


@pytest.mark.parametrize(
    "window_length, gap",
    [
        (3, 2),
        (3, 4),  # gap larger than window
        (2, 0),  # gap explicitly set to 0
        ('3d', '2d'),  # using offset aliases
        (4, '1d'),  # using mixture of integer and offset aliases
        ('2d', 2)  # using mixture of integer and offset aliases
    ],
)
def test_roll_series_with_gap(window_length, gap, rolling_series_pd):
    rolling_max = _roll_series_with_gap(rolling_series_pd, window_length, gap=gap).max()
    rolling_min = _roll_series_with_gap(rolling_series_pd, window_length, gap=gap).min()

    assert len(rolling_max) == len(rolling_series_pd)
    assert len(rolling_min) == len(rolling_series_pd)

    gap = get_number_of_days(gap)
    window_length = get_number_of_days(window_length)
    for i in range(len(rolling_series_pd)):
        start_idx = i - gap - window_length + 1
        end_idx = i - gap

        # If start and end are negative, they're entirely before
        if start_idx < 0 and end_idx < 0:
            assert pd.isnull(rolling_max.iloc[i])
            assert pd.isnull(rolling_min.iloc[i])
            continue

        if start_idx < 0:
            start_idx = 0

        # Because the row values are a range from 0 to 20, the rolling min will be the start index
        # and the rolling max will be the end idx
        assert rolling_min.iloc[i] == start_idx
        assert rolling_max.iloc[i] == end_idx


def test_roll_series_with_no_gap(rolling_series_pd):
    window_length = 3
    gap = 0
    actual_rolling = _roll_series_with_gap(rolling_series_pd, window_length, gap=gap).mean()
    expected_rolling = rolling_series_pd.rolling(window_length, min_periods=1).mean()

    pd.testing.assert_series_equal(actual_rolling, expected_rolling)


@pytest.mark.parametrize(
    "window_length, gap",
    [
        (6, 2),
        (6, 0),  # No gap - changes early values
        ('6d', '0d')  # Uses offset aliases
    ]
)
def test_roll_series_with_gap_early_values(window_length, gap, rolling_series_pd):
    gap_num = get_number_of_days(gap)
    window_length_num = get_number_of_days(window_length)

    # Default min periods is 1 - will include all
    default_partial_values = _roll_series_with_gap(rolling_series_pd,
                                                   window_length,
                                                   gap=gap).count()
    num_empty_aggregates = len(default_partial_values.loc[default_partial_values == 0])
    num_partial_aggregates = len((default_partial_values
                                  .loc[default_partial_values != 0])
                                 .loc[default_partial_values < window_length_num])
    assert num_empty_aggregates == gap_num
    assert num_partial_aggregates == window_length_num - 1

    # Make min periods the size of the window
    no_partial_values = _roll_series_with_gap(rolling_series_pd,
                                              window_length,
                                              gap=gap,
                                              min_periods=window_length_num).count()
    num_null_aggregates = len(no_partial_values.loc[pd.isna(no_partial_values)])
    num_partial_aggregates = len(no_partial_values.loc[no_partial_values < window_length_num])

    # because we shift, gap is included as nan values in the series.
    # Count treats nans in a window as values that don't get counted,
    # so the gap rows get included in the count for whether a window has "min periods".
    # This is different than max, for example, which does not count nans in a window as values towards "min periods"
    assert num_null_aggregates == window_length_num - 1
    assert num_partial_aggregates == gap_num


def test_roll_series_with_gap_nullable_types(rolling_series_pd):
    window_length = 3
    gap = 2
    # Because we're inserting nans, confirm that nullability of the dtype doesn't have an impact on the results
    nullable_series = rolling_series_pd.astype('Int64')
    non_nullable_series = rolling_series_pd.astype('int64')

    nullable_rolling_max = _roll_series_with_gap(nullable_series, window_length, gap=gap).max()
    non_nullable_rolling_max = _roll_series_with_gap(non_nullable_series, window_length, gap=gap).max()

    pd.testing.assert_series_equal(nullable_rolling_max, non_nullable_rolling_max)


def test_roll_series_with_gap_nullable_types_with_nans(rolling_series_pd):
    window_length = 3
    gap = 2
    nullable_floats = rolling_series_pd.astype('float64').replace({1: np.nan, 3: np.nan})
    nullable_ints = nullable_floats.astype('Int64')

    nullable_ints_rolling_max = _roll_series_with_gap(nullable_ints, window_length, gap=gap).max()
    nullable_floats_rolling_max = _roll_series_with_gap(nullable_floats, window_length, gap=gap).max()

    pd.testing.assert_series_equal(nullable_ints_rolling_max, nullable_floats_rolling_max)

    expected_early_values = ([np.nan, np.nan, 0, 0, 2, 2, 4] +
                             list(range(7 - gap, len(rolling_series_pd) - gap)))
    for i in range(len(rolling_series_pd)):
        actual = nullable_floats_rolling_max.iloc[i]
        expected = expected_early_values[i]

        if pd.isnull(actual):
            assert pd.isnull(expected)
        else:
            assert actual == expected


def test_roll_series_with_gap_and_non_fixed_offset_gap():
    # --> clean up more
    # The offset of 1W is <Week: weekday=6>, so the gap will make the start
    # the first 6th day of the week after the first datetime, not 7 days after the first datetime
    starts_on_sunday = pd.Series(range(40), index=pd.date_range(start='2017-1-15', freq='1D', periods=40))

    rolled_series = _roll_series_with_gap(starts_on_sunday, "5D", gap="1M", min_periods=1).max()
    assert rolled_series.isna().sum() == 16

    rolled_series = _roll_series_with_gap(starts_on_sunday, "5D", gap="1W", min_periods=1).max()
    assert rolled_series.isna().sum() == 7

    starts_on_monday = pd.Series(range(40), index=pd.date_range(start='2017-01-16', freq='1D', periods=40))

    rolled_series = _roll_series_with_gap(starts_on_monday, "5D", gap="1W", min_periods=1).max()
    assert rolled_series.isna().sum() == 6

    rolled_series = _roll_series_with_gap(starts_on_monday, "5D", gap="1M", min_periods=1).max()
    assert rolled_series.isna().sum() == 15


def test_roll_series_with_gap_non_uniform_impact_gap():
    # When there is a large distance between the first and second rows
    # the gap will still use the first value, so this impacts the number of rows of nans we get
    datetimes = list(pd.date_range(start='2020-01-01', freq='1d', periods=20))
    datetimes[0] = datetimes[0] - pd.Timedelta('10D')
    no_freq_series = pd.Series(range(20), index=datetimes)

    assert pd.infer_freq(no_freq_series.index) is None

    window_length = '5d'

    # Only one is within the bounds
    rolled_series = _roll_series_with_gap(no_freq_series, window_length, gap="1W", min_periods=1).max()
    assert rolled_series.isna().sum() == 1

    # 2 weeks starts to include some other data
    rolled_series = _roll_series_with_gap(no_freq_series, window_length, gap="2W", min_periods=1).max()
    assert rolled_series.isna().sum() == 4

    # 3 weeks is where we get a full week for the first time
    rolled_series = _roll_series_with_gap(no_freq_series, window_length, gap="3W", min_periods=1).max()
    assert rolled_series.isna().sum() == 11


def test_roll_series_with_gap_non_uniform_impacts_window_length():
    # When the data isn't uniform, this impacts the number of values in each rolling window
    pass


def test_roll_series_with_gap_invalid_offset_strings():
    pass


def test_roll_series_with_gap_offsets_gap_isnt_multiple_of_data_freq():
    # will produce odd results since shift will move all the index values weirdly
    pass


def test_roll_series_with_gap_offsets_larger_than_data_freq():
    pass


def test_roll_series_with_gap_no_datetime():
    pass


def test_roll_series_with_gap_different_freq():
    # confirm different frequencies of data and
    pass
