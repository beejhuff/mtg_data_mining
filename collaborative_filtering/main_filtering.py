import os
import json
from tqdm import tqdm
from loader_magic import MagicLoader, DeckManager
from collaborative_filtering.item_to_item import ItemToItem, Rating
from lsa_encoder import DataCleaner, LSAEncoder, LSAManager
from database.db_redis import DBRedis
from queue import Queue
from threading import Thread


from time import time
import numpy as np

def encoding_magic_card(card_loader):
    lsa_manager = LSAManager(card_loader.hash_id_texts)
    lsa_manager.encode()
    return lsa_manager

def load_magic_environment():
    print('Load deck')
    card_loader = MagicLoader()
    card_loader.load('./../data/magic_cards/AllCards-x.json')
    return card_loader

def load_decks_database(card_loader):
    print('Clean deck')
    deck_loader = DeckManager()


    files = os.listdir("./../data/decks_mtgdeck_net")  # returns list
    paths = []
    for file in files:
        paths.append('./../data/decks_mtgdeck_net/' + file)
    deck_loader.load_from_mtgdeck_csv(paths, card_loader)
    deck_loader.extract_lands(card_loader.lands, card_loader)
    deck_loader.sort_decks()

    '''
    list_files = os.listdir("./../db_decks")  # returns list
    deck_loader.load_from_csv(list_files, card_loader)
    deck_loader.extract_lands(card_loader.lands, card_loader)
    '''

    return deck_loader

def test_build_tree(deck_loader):
    ratings = []
    #max_len = 0
    for card in tqdm(deck_loader.cards):
        current_value = int(card in deck_loader.decks[0])

        rating = Rating(current_value)
        nb_values = 0
        for deck in deck_loader.decks:
            new_val = int(card in deck)

            if new_val == current_value:
                nb_values += 1
            else:
                rating.compression.append(nb_values)
                nb_values = 1
                current_value = new_val
        ratings.append(rating)
        #if len(rating.compression) > max_len:
        #    max_len = len(rating.compression)
        #    print(max_len)

    for rating in ratings:
        rating.uncompress()

def global_recommandation():
    print('Load magic environment')
    card_loader = load_magic_environment()
    deck_loader = load_decks_database(card_loader)

    print('Convert card text into vector')
    lsa_manager = encoding_magic_card(card_loader)

    catalog = sorted(list(deck_loader.cards))
    item_recommender = ItemToItem(list(deck_loader.cards))
    print('Get ratings')
    item_recommender.load_ratings(deck_loader.decks)
    print('Compute similarities')
    item_recommender.compute_similarities(deck_loader.decks)

    print('Get recommendations for 16622')
    recommendations = item_recommender.get_recommendation(16622, 10, lsa_manager)
    print('Recommendation for ' + str(card_loader.hash_id_name[16622]) + ':')  # 16622, 620
    for id_card, score in recommendations.items():
        print('   - ' + str(card_loader.hash_id_name[id_card]) + ': ' + str(score))

    print('Get recommendations for 620')
    recommendations = item_recommender.get_recommendation(620, 10, lsa_manager)
    print('Recommendation for ' + str(card_loader.hash_id_name[620]) + ':')  # 16622, 620
    for id_card, score in recommendations.items():
        print('   - ' + str(card_loader.hash_id_name[id_card]) + ': ' + str(score))

    similiraties = {}
    for id_card in catalog:
        recommendations = item_recommender.get_recommendation(id_card, 5, lsa_manager)
        suggestions = {}
        for id_rec, score in recommendations.items():
            suggestions[card_loader.hash_id_name[id_rec]] = {'item_similarity': score[0],
                                                             'content_similarity': score[1]}
        similiraties[card_loader.hash_id_name[id_card]] = suggestions

    with open('./../similarities.json', 'w') as f:
        json.dump(similiraties, f)


def grouped_recommandations():
    print('Load magic environment')
    card_loader = load_magic_environment()
    deck_loader = load_decks_database(card_loader)

    print('Convert card text into vector')
    lsa_manager = encoding_magic_card(card_loader)

    similiraties = {}
    for game_mode in deck_loader.grouped_decks.keys():
        for color in deck_loader.grouped_decks[game_mode].keys():
            print('Process mode: ' + str(game_mode) + ', color: ' + str(color))
            deck_database = deck_loader.grouped_decks[game_mode][color]
            card_catalog = deck_loader.grouped_cards[game_mode][color]

            item_recommender = ItemToItem(list(card_catalog))
            print('Get ratings')
            item_recommender.load_ratings(deck_database)
            print('Compute similarities')
            item_recommender.compute_similarities(deck_database)

            print('Get recommandations')
            for id_card in tqdm(card_catalog):
                if card_loader.hash_id_name[id_card] not in similiraties:
                    similiraties[card_loader.hash_id_name[id_card]] = {}

                recommendations = item_recommender.get_recommendation(id_card, 5, lsa_manager)
                suggestions = {}
                for id_rec, score in recommendations.items():
                    suggestions[card_loader.hash_id_name[id_rec]] = {'item_similarity': score[0],
                                                                     'content_similarity': score[1]}

                if game_mode not in similiraties[card_loader.hash_id_name[id_card]]:
                    similiraties[card_loader.hash_id_name[id_card]][game_mode] = {}

                if game_mode not in similiraties[card_loader.hash_id_name[id_card]][game_mode]:
                    similiraties[card_loader.hash_id_name[id_card]][game_mode][color] = None

                similiraties[card_loader.hash_id_name[id_card]][game_mode][color] = suggestions

    with open('./../similarities.json', 'w') as f:
        json.dump(similiraties, f)

def job(game_mode, game_colors, game_card_catalog, game_deck_database, hash_id_name, lsa_manager, queue):
    print('Process ratings and similarities for ' + str(game_mode))

    print('Get recommandations for ' + str(game_mode))
    similiraties = {}
    for color in game_colors:
        print('Process color: ' + str(color) + ' for ' + str(game_mode))
        deck_database = game_deck_database[color]
        card_catalog = game_card_catalog[color]

        item_recommender = ItemToItem(list(card_catalog))
        item_recommender.load_ratings(deck_database)
        item_recommender.compute_similarities(deck_database)

        for id_card in card_catalog:
            if hash_id_name[id_card] not in similiraties:
                similiraties[hash_id_name[id_card]] = {}

            recommendations = item_recommender.get_recommendation(id_card, 5, lsa_manager)
            suggestions = {}
            for id_rec, score in recommendations.items():
                suggestions[hash_id_name[id_rec]] = {'item_similarity': score[0],
                                                     'content_similarity': score[1]}

            if game_mode not in similiraties[hash_id_name[id_card]]:
                similiraties[hash_id_name[id_card]][game_mode] = {}

            if game_mode not in similiraties[hash_id_name[id_card]][game_mode]:
                similiraties[hash_id_name[id_card]][game_mode][color] = None

            similiraties[hash_id_name[id_card]][game_mode][color] = suggestions

    queue.put(similiraties)

def test_multi_thread():
    print('Load magic environment')
    card_loader = load_magic_environment()
    deck_loader = load_decks_database(card_loader)

    print('Convert card text into vector')
    lsa_manager = encoding_magic_card(card_loader)

    queue = Queue()
    thread_pull = []
    for game_mode in deck_loader.grouped_decks.keys():
        game_colors = deck_loader.grouped_decks[game_mode].keys()
        deck_database = deck_loader.grouped_decks[game_mode]
        card_catalog = deck_loader.grouped_cards[game_mode]

        thread_ = Thread(
            target=job,
            name="Thread1",
            args=[game_mode, game_colors, card_catalog, deck_database, card_loader.hash_id_name, lsa_manager, queue],
        )
        thread_pull.append(thread_)

    for thread_ in thread_pull:
        thread_.start()

    for thread_ in thread_pull:
        thread_.join()

    print('End processing ratings and similarities')
    print('Consolidate results')
    similiraties = {}
    for game_similarity in iter(queue.get, None):
        for card in game_similarity.keys():
            if card not in similiraties:
                similiraties[card] = {}

            for game_mode in game_similarity[card].keys():
                similiraties[card][game_mode] = game_similarity[card][game_similarity]

    print('Save data into json')
    with open('./../similarities_multi.json', 'w') as f:
        json.dump(similiraties, f)

if __name__ == "__main__":
    #grouped_recommandations()
    test_multi_thread()