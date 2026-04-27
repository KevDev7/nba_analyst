{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve.Common.ValueCanonicalization
  ( canonicalizeTextValue
  ) where

import Data.Text (Text)
import qualified Data.Text as T

canonicalizeTextValue :: Text -> Text -> Text -> Text
canonicalizeTextValue targetObjectName attributeName rawValue =
  -- Normalize user-facing aliases only after the ontology has identified the
  -- exact object + attribute. Unknown values pass through to avoid narrowing
  -- valid ontology-backed filters.
  case (targetObjectName, attributeName) of
    ("Team", "conference") -> maybe rawValue id (canonicalConference rawValue)
    ("Team", "division") -> maybe rawValue id (canonicalDivision rawValue)
    ("Team", "team_name") -> maybe rawValue id (canonicalTeamName rawValue)
    ("Team", "team_abbreviation") -> maybe rawValue id (canonicalTeamAbbreviation rawValue)
    _ -> rawValue

canonicalConference :: Text -> Maybe Text
canonicalConference rawValue =
  case normalizedValue rawValue of
    "east" -> Just "east"
    "eastern" -> Just "east"
    "easternconference" -> Just "east"
    "west" -> Just "west"
    "western" -> Just "west"
    "westernconference" -> Just "west"
    _ -> Nothing

canonicalDivision :: Text -> Maybe Text
canonicalDivision rawValue =
  case normalizedValue rawValue of
    "atlantic" -> Just "Atlantic"
    "atlanticdivision" -> Just "Atlantic"
    "central" -> Just "Central"
    "centraldivision" -> Just "Central"
    "southeast" -> Just "Southeast"
    "southeastdivision" -> Just "Southeast"
    "northwest" -> Just "Northwest"
    "northwestdivision" -> Just "Northwest"
    "pacific" -> Just "Pacific"
    "pacificdivision" -> Just "Pacific"
    "southwest" -> Just "Southwest"
    "southwestdivision" -> Just "Southwest"
    _ -> Nothing

canonicalTeamName :: Text -> Maybe Text
canonicalTeamName rawValue =
  case normalizedValue rawValue of
    "atl" -> Just "Hawks"
    "atlantahawks" -> Just "Hawks"
    "hawks" -> Just "Hawks"
    "bos" -> Just "Celtics"
    "bostonceltics" -> Just "Celtics"
    "celtics" -> Just "Celtics"
    "bkn" -> Just "Nets"
    "brooklynnets" -> Just "Nets"
    "nets" -> Just "Nets"
    "cha" -> Just "Hornets"
    "charlottehornets" -> Just "Hornets"
    "hornets" -> Just "Hornets"
    "chi" -> Just "Bulls"
    "chicagobulls" -> Just "Bulls"
    "bulls" -> Just "Bulls"
    "cle" -> Just "Cavaliers"
    "clevelandcavaliers" -> Just "Cavaliers"
    "cavs" -> Just "Cavaliers"
    "cavaliers" -> Just "Cavaliers"
    "dal" -> Just "Mavericks"
    "dallasmavericks" -> Just "Mavericks"
    "mavs" -> Just "Mavericks"
    "mavericks" -> Just "Mavericks"
    "den" -> Just "Nuggets"
    "denvernuggets" -> Just "Nuggets"
    "nuggets" -> Just "Nuggets"
    "det" -> Just "Pistons"
    "detroitpistons" -> Just "Pistons"
    "pistons" -> Just "Pistons"
    "gsw" -> Just "Warriors"
    "goldenstatewarriors" -> Just "Warriors"
    "warriors" -> Just "Warriors"
    "hou" -> Just "Rockets"
    "houstonrockets" -> Just "Rockets"
    "rockets" -> Just "Rockets"
    "ind" -> Just "Pacers"
    "indianapacers" -> Just "Pacers"
    "pacers" -> Just "Pacers"
    "lac" -> Just "Clippers"
    "laclippers" -> Just "Clippers"
    "losangelesclippers" -> Just "Clippers"
    "clippers" -> Just "Clippers"
    "lal" -> Just "Lakers"
    "lalakers" -> Just "Lakers"
    "lalaker" -> Just "Lakers"
    "losangeleslakers" -> Just "Lakers"
    "lakers" -> Just "Lakers"
    "mem" -> Just "Grizzlies"
    "memphisgrizzlies" -> Just "Grizzlies"
    "grizzlies" -> Just "Grizzlies"
    "mia" -> Just "Heat"
    "miamiheat" -> Just "Heat"
    "heat" -> Just "Heat"
    "mil" -> Just "Bucks"
    "milwaukeebucks" -> Just "Bucks"
    "bucks" -> Just "Bucks"
    "min" -> Just "Timberwolves"
    "minnesotatimberwolves" -> Just "Timberwolves"
    "wolves" -> Just "Timberwolves"
    "timberwolves" -> Just "Timberwolves"
    "nop" -> Just "Pelicans"
    "neworleanspelicans" -> Just "Pelicans"
    "pelicans" -> Just "Pelicans"
    "nyk" -> Just "Knicks"
    "newyorkknicks" -> Just "Knicks"
    "knicks" -> Just "Knicks"
    "okc" -> Just "Thunder"
    "oklahomacitythunder" -> Just "Thunder"
    "thunder" -> Just "Thunder"
    "orl" -> Just "Magic"
    "orlandomagic" -> Just "Magic"
    "magic" -> Just "Magic"
    "phi" -> Just "76ers"
    "phila" -> Just "76ers"
    "philadelphia76ers" -> Just "76ers"
    "philadelphiaseventysixers" -> Just "76ers"
    "sixers" -> Just "76ers"
    "76ers" -> Just "76ers"
    "phx" -> Just "Suns"
    "phoenixsuns" -> Just "Suns"
    "suns" -> Just "Suns"
    "por" -> Just "Trail Blazers"
    "portlandtrailblazers" -> Just "Trail Blazers"
    "trailblazers" -> Just "Trail Blazers"
    "blazers" -> Just "Trail Blazers"
    "sac" -> Just "Kings"
    "sacramentokings" -> Just "Kings"
    "kings" -> Just "Kings"
    "sas" -> Just "Spurs"
    "sanantoniospurs" -> Just "Spurs"
    "spurs" -> Just "Spurs"
    "tor" -> Just "Raptors"
    "torontoraptors" -> Just "Raptors"
    "raptors" -> Just "Raptors"
    "uta" -> Just "Jazz"
    "utahjazz" -> Just "Jazz"
    "jazz" -> Just "Jazz"
    "was" -> Just "Wizards"
    "washingtonwizards" -> Just "Wizards"
    "wizards" -> Just "Wizards"
    _ -> Nothing

canonicalTeamAbbreviation :: Text -> Maybe Text
canonicalTeamAbbreviation rawValue =
  case canonicalTeamName rawValue of
    Just "Hawks" -> Just "ATL"
    Just "Celtics" -> Just "BOS"
    Just "Nets" -> Just "BKN"
    Just "Hornets" -> Just "CHA"
    Just "Bulls" -> Just "CHI"
    Just "Cavaliers" -> Just "CLE"
    Just "Mavericks" -> Just "DAL"
    Just "Nuggets" -> Just "DEN"
    Just "Pistons" -> Just "DET"
    Just "Warriors" -> Just "GSW"
    Just "Rockets" -> Just "HOU"
    Just "Pacers" -> Just "IND"
    Just "Clippers" -> Just "LAC"
    Just "Lakers" -> Just "LAL"
    Just "Grizzlies" -> Just "MEM"
    Just "Heat" -> Just "MIA"
    Just "Bucks" -> Just "MIL"
    Just "Timberwolves" -> Just "MIN"
    Just "Pelicans" -> Just "NOP"
    Just "Knicks" -> Just "NYK"
    Just "Thunder" -> Just "OKC"
    Just "Magic" -> Just "ORL"
    Just "76ers" -> Just "PHI"
    Just "Suns" -> Just "PHX"
    Just "Trail Blazers" -> Just "POR"
    Just "Kings" -> Just "SAC"
    Just "Spurs" -> Just "SAS"
    Just "Raptors" -> Just "TOR"
    Just "Jazz" -> Just "UTA"
    Just "Wizards" -> Just "WAS"
    _ -> Nothing

normalizedValue :: Text -> Text
normalizedValue =
  T.filter isAliasCharacter . T.toLower . T.strip

isAliasCharacter :: Char -> Bool
isAliasCharacter character =
  ('a' <= character && character <= 'z') || ('0' <= character && character <= '9')
