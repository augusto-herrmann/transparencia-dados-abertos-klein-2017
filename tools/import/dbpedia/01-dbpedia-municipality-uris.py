# 01-dbpedia-municipality-uris.py
"""
 This script fetches the municipalities URIs from DBPedia.
 
 Este script traz as URIs de municípios da DBPedia.
"""

import re
import os
import urllib
import pandas as pd
from frictionless import Package

GEO_FOLDER = '../../../data/auxiliary/geographic'
GEO_FILE = 'municipality.csv'
OUTPUT_FOLDER = '../../../data/auxiliary/geographic'
OUTPUT_FILE = 'municipality.csv'

remove_parenthesis = re.compile(r'[^(,]+')

DBPEDIA_PT_SPARQL = 'dbpedia-pt.sparql'
DBPEDIA_SPARQL = 'dbpedia.sparql'
DBPEDIA_PT_URL = 'http://pt.dbpedia.org/sparql?default-graph-uri=&{}&should-sponge=&format=text%2Fcsv&timeout=0&debug=on'
DBPEDIA_URL = 'http://dbpedia.org/sparql?default-graph-uri=http%3A%2F%2Fdbpedia.org&&format=text%2Fcsv&CXML_redir_for_subjs=121&CXML_redir_for_hrefs=&timeout=30000&debug=on&run=+Run+Query+'


def update_column(
    old_df: pd.DataFrame,
    new_df:pd.DataFrame,
    column: str
    ) -> pd.DataFrame:
    "Update the column in the old dataframe with data from the same column in the new dataframe"
    
    return old_df[column].combine(
        new_df[column],
        lambda old_URI, new_URI: old_URI if new_URI is None else new_URI
    ) if column in old_df.columns else new_df[column]

def update_from_dbpedia(
    output_file: str,
    geo_file: str,
    sparql_file: str,
    sparql_query_url: str
    ):
    """Makes a DBPedia query to retrieve data about municipalities and
    updates the csv file.
    """
    
    # read SPARQL query
    with open (sparql_file, 'r') as f:
        sparql_query = urllib.parse.urlencode({'query':f.read()})
    
    # get query URL
    sparql_query_as_csv = sparql_query_url.format(sparql_query)

    # read data frame from Portuguese DBPedia
    dbp_pt = pd.read_csv(sparql_query_as_csv)

    # remove parenthesis in city names
    dbp_pt['name'] = dbp_pt.name.apply(
        lambda s: remove_parenthesis.match(s).group().strip()
    )

    # get WikiData URIs for later
    wikidata = (
        dbp_pt
        .loc[:, ['name', 'state', 'wikidata']]
        .loc[dbp_pt.state.notna()]
        .loc[dbp_pt.wikidata.notna()]
        .drop_duplicates()
        .copy()
    )

    # get the state (UF) abbreviations as the DBPedia data does not contain them
    package = Package(
        os.path.join(os.path.dirname(geo_file),'datapackage.json')
    )
    uf = package.get_resource('uf').to_pandas()

    # adjust column names and types
    uf.rename(columns={'name': 'state'}, inplace=True)
    uf.drop('code', axis=1, inplace=True)
    uf['state'] = uf['state'].astype('category')

    # get state abbreviations for wikidata df
    wikidata = (
        wikidata
        .merge(uf)
        .loc[:, ['name', 'abbr', 'wikidata']]
        .rename(columns={'abbr': 'uf'})
    )

    # handle the different types of URIs – main DBPedia or pt DBPedia
    dbp_pt['URI_type'] = dbp_pt.city.apply(
        lambda s: 'dbpedia' \
            if s.startswith('http://dbpedia.org/') \
            else 'dbpedia_pt' \
                if s.startswith('http://pt.dbpedia.org/') \
                    else None
    )

    # format the dataframe like the municipality table
    dbp_pt = dbp_pt.merge(uf)
    dbp_pt.drop('state', axis=1, inplace=True)
    dbp_pt.rename(columns={'abbr': 'uf'}, inplace=True)
    dbp_pt.rename(columns={'city': 'URI'}, inplace=True)
    dbp_pt = dbp_pt.loc[:, ['name', 'uf', 'URI', 'URI_type']] # discard all other columns
    dbp_pt.sort_values(by=['uf', 'name', 'URI'], inplace=True)
    dbp_pt.drop_duplicates(subset=['name', 'uf', 'URI_type'], keep='first', inplace=True)

    # create dbpedia and dbpedia_pt columns depending on the value of URI
    dbp_pt = (
        dbp_pt
        .merge(
            (
                dbp_pt
                .pivot(index=['name', 'uf'], columns='URI_type', values='URI')
                .reindex()
            ), on=['name', 'uf'], how='left'
        )
        .drop(['URI', 'URI_type'], axis=1)
        .drop_duplicates()
    )

    # get the municipality codes as the DBPedia data does not contain them
    mun = package.get_resource('municipality').to_pandas()

    # just add the municipality codes to the dataframe
    dbp_pt = dbp_pt.merge( 
        mun.loc[:, ['code', 'name', 'uf']], # use just those columns for merge
        on=['name', 'uf'], # keys for the join operation
        how='right', # keep the keys from mun dataframe even if not found on dbp_pt
    ).reindex(columns=['code', 'name', 'uf', 'dbpedia', 'dbpedia_pt'])

    # add wikidata column to dbp_pt again
    dbp_pt = (
        dbp_pt
        .merge(wikidata, on=['name', 'uf'], how='left')
    )

    # sort both dataframes to align them
    assert len(dbp_pt) == len(mun) # must be the same size
    dbp_pt.sort_values(by='code', inplace=True)
    mun.sort_values(by='code', inplace=True)
    dbp_pt.set_index(dbp_pt.code, inplace=True) # make the index be the code
    mun.set_index(mun.code, inplace=True) # make the index be the code

    # update the URIs, if present. Otherwise, preserve the old ones
    mun['dbpedia'] = update_column(mun, dbp_pt, 'dbpedia')
    mun['dbpedia_pt'] = update_column(mun, dbp_pt, 'dbpedia_pt')
    mun['wikidata'] = update_column(mun, dbp_pt, 'wikidata')

    # write back the csv
    mun.to_csv(output_file, index=False)

if __name__ == '__main__':
    # from Portuguese language DBPedia
    update_from_dbpedia(
        os.path.join(OUTPUT_FOLDER, OUTPUT_FILE),
        os.path.join(GEO_FOLDER, GEO_FILE),
        DBPEDIA_PT_SPARQL,
        DBPEDIA_PT_URL
    )
    # from English DBPedia
    # update_from_dbpedia(
    #     os.path.join(OUTPUT_FOLDER, OUTPUT_FILE),
    #     os.path.join(GEO_FOLDER, GEO_FILE),
    #     DBPEDIA_SPARQL,
    #     DBPEDIA_URL
    # )
