from tools.torznab_fixture import attributes, matching


def test_original_fixture_defaults_remain_compatible():
    movie = {'kind': 'movie', 'size': 1, 'hash': 'original'}
    assert attributes(movie)['tmdbid'] == '10331'
    assert matching([movie], 'movie', {'imdbid': ['tt0063350']}) == [movie]
    assert matching([movie], 'tvsearch', {}) == []


def test_multiple_titles_keep_their_identity_and_resolution_categories():
    rows = [{'kind': 'movie', 'size': 1, 'hash': str(number), 'category': category,
             'identities': {'tmdbid': '329', 'imdb': '0107290'}}
            for number, category in enumerate(('2030', '2040', '2045'))]
    another = rows[0] | {'identities': {'tmdbid': '1542', 'imdb': '0151804'}}
    assert matching([*rows, another], 'movie', {'tmdbid': ['329']}) == rows
    assert matching([*rows, another], 'movie', {'imdbid': ['tt0107290']}) == rows
    assert [attributes(row)['category'] for row in rows] == ['2030', '2040', '2045']


def test_episode_search_does_not_return_another_show_or_episode():
    row = {'kind': 'tv', 'size': 1, 'hash': 'episode', 'identities': {'tvdbid': '73871'},
           'season': 1, 'episode': 1}
    assert matching([row], 'tvsearch', {'tvdbid': ['73871'], 'season': ['1'], 'ep': ['1']}) == [row]
    for query in ({'tvdbid': ['72658']}, {'season': ['2']}, {'ep': ['2']}):
        assert matching([row], 'tvsearch', query) == []
