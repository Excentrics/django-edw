# -*- coding: utf-8 -*-

import json
from collections import Counter
# from math import log

from haystack import connections


# def get_more_like_this(text, entity_model=None, stop_words=None):
def get_more_like_this(like, model=None):
    """
    Perform `more_like_this` query to find similar model instances.

    `entity_model` is like 'particularproblem', 'typicalestablishment', etc.

    `stop_words` is a list of stopwords to make search results better.
    Common Russian stopwords are already filtered in search backend,
    this list must only contain words specific to the entity model.
    """

    backend = connections['default'].get_backend()

    unlike = 'городской округ сельское поселение больница школа ижс'
    ignore = 'ижс'

    payload = {
        'query': {
            'bool': {
                'must': [
                    {
                        'more_like_this': {
                            'fields': ['title', 'description', 'characteristics'],
                            'like': like,
                            # 'unlike': unlike,
                            # 'min_word_length': 2,

                            'min_term_freq': 1,
                            'min_doc_freq': 1,
                            'max_query_terms': 25,
                            'minimum_should_match': '0%',
                            'analyzer': 'default',
                        }
                    }
                ],
                # 'should': [
                #     {
                #         'more_like_this': {
                #             'fields': ['title', 'text', 'characteristics'],
                #             'like': 'больница детский сад школа парк',
                #             # 'unlike': unlike,
                #             'min_term_freq': 1,
                #             'min_doc_freq': 1,
                #             'max_query_terms': 25,
                #             'minimum_should_match': '0%',
                #             'analyzer': 'default',
                #             'stop_words': stop_words or []
                #         }
                #     }
                # ],
                'must_not': [
                    {
                        'more_like_this': {
                            'fields': ['title', 'description', 'characteristics'],
                            # 'like': 'тротуар поселение',
                            # 'like': 'ижс сельский региональный',
                            'like': unlike,
                            'unlike': ignore,
                            'min_term_freq': 1,
                            'min_doc_freq': 1,
                            'max_query_terms': 12,
                            'minimum_should_match': '0%',
                            'analyzer': 'default',
                        }
                    }
                ]
            }
        }
    }
    if model:
        payload['query']['bool']['filter'] = [
            {
                'term': {
                    'model': model,
                }
            }
        ]

    search_result = backend.conn.search(
        body=payload,
        index=backend.index_name,
        doc_type='modelresult',
        explain=True,
        _source=True,
        size=10,
    )
    return search_result


def analyze_suggestions(search_result):
    """
    Sort and filter `get_more_like_this` suggestions to classify category.
    """

    # print('----- search_result -----', search_result)
    # print()
    # print()
    # print()

    # Parse search result to get score and words per suggestion
    suggestions = {}
    for hit in search_result['hits']['hits']:
        # When querying all models at the same time,
        # some of them may have [None] in category field,
        # so we ignore them
        raw_categories = hit['_source']['categories']
        if not raw_categories:
            continue
        words = set()

        print ()
        print('----- hit[_explanation][details] --------->>>>>>', hit['_explanation'])
        print ()

        # формируем список ключевых слов
        for raw_word_details in hit['_explanation']['details']:

            # print ("!!! detail len", len(raw_word_details['details']))
            details_sources = raw_word_details['details'] + [raw_word_details]

            # for word_details in (raw_word_details['details'][0], raw_word_details):
            # todo: переписать!!!
            for word_details in details_sources:
                try:
                    words.add(word_details['description'].replace('weight(', '').split(' ')[0].split(':')[1])
                except IndexError:
                    # print ("@@ IndexError @@")
                    pass
                # else:
                #     print ("@@ Index OK   @@")
                #     pass
                #     # break

            # print ("WORDS!", words)
        # накапливаем результат
        for x in raw_categories:
            try:
                category = json.loads(x)
            except json.decoder.JSONDecodeError:
                pass
            else:
                score = hit['_score'] if category.get('similar', True) else -hit['_score']
                foo = suggestions.get(x, None)
                if foo is None:
                    suggestions[x] = {
                        'category': category,
                        'words': words,
                        'score': score
                    }
                else:
                    foo['score'] += score
                    foo['words'].update(words)
    # переводим множество слов в список
    suggestions = suggestions.values()
    for x in suggestions:
        x['words'] = list(x['words'])
    # сортируем
    suggestions = sorted(
        suggestions,
        key=lambda x: x['score'],
        reverse=True
    )

    print('>>> suggestions >>> ')
    for x in suggestions[:5]:
        print('------------------')
        print('* id:', x['category']['id'])
        print('* category:', x['category']['name'])
        print('* score:', x['score'])
        print('* words:', x['words'])

    print('>>>>>>>>>>>>>>>>>>>>')


    return suggestions