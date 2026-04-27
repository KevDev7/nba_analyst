{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve.Common.DisplayMetadata
  ( resolveDisplayMetadata
  ) where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Resolve.Common.Types
import OntologyLayer.Graph (findAttribute)
import qualified OntologyLayer.Types as OT

resolveDisplayMetadata :: OT.Object -> OT.Object -> Int -> [ResolvedDisplayMetadata]
resolveDisplayMetadata factObject rowObject windowGames =
  if windowGames > 0
    then recentDisplayMetadata factObject rowObject
    else seasonDisplayMetadata factObject rowObject

recentDisplayMetadata :: OT.Object -> OT.Object -> [ResolvedDisplayMetadata]
recentDisplayMetadata factObject rowObject =
  gamesPlayedCountMetadata
    : (if isPlayerRowObject rowObject
         then maybeToList (minutesAverageMetadata factObject)
         else [])
    <> maybeToList (dateRangeEvidenceMetadata factObject)

seasonDisplayMetadata :: OT.Object -> OT.Object -> [ResolvedDisplayMetadata]
seasonDisplayMetadata factObject rowObject =
  maybeToList (identityMetadata "games_played" "Games Played" "games_played" factObject)
    <> if isPlayerRowObject rowObject
        then maybeToList (seasonMinutesMetadata factObject)
        else []

gamesPlayedCountMetadata :: ResolvedDisplayMetadata
gamesPlayedCountMetadata =
  ResolvedDisplayMetadata
    { metadataKey = "games_played"
    , metadataLabel = "Games Played"
    , metadataColumnType = "analytical_metadata"
    , metadataSource = Nothing
    , metadataAggregation = "count_rows"
    }

minutesAverageMetadata :: OT.Object -> Maybe ResolvedDisplayMetadata
minutesAverageMetadata =
  sourceMetadata "minutes" "Minutes" "minutes_played" "avg"

dateRangeEvidenceMetadata :: OT.Object -> Maybe ResolvedDisplayMetadata
dateRangeEvidenceMetadata =
  sourceMetadataOfType "date_range" "Date Range" "evidence" "game_date" "date_range"

seasonMinutesMetadata :: OT.Object -> Maybe ResolvedDisplayMetadata
seasonMinutesMetadata factObject =
  firstJust
    [ identityMetadata "minutes" "Minutes" "minutes_per_game" factObject
    , identityMetadata "minutes" "Minutes" "minutes" factObject
    ]

identityMetadata :: Text -> Text -> Text -> OT.Object -> Maybe ResolvedDisplayMetadata
identityMetadata keyValue labelValue attributeName factObject =
  sourceMetadata keyValue labelValue attributeName "identity" factObject

sourceMetadata :: Text -> Text -> Text -> Text -> OT.Object -> Maybe ResolvedDisplayMetadata
sourceMetadata keyValue labelValue attributeName aggregationValue =
  sourceMetadataOfType keyValue labelValue "analytical_metadata" attributeName aggregationValue

sourceMetadataOfType :: Text -> Text -> Text -> Text -> Text -> OT.Object -> Maybe ResolvedDisplayMetadata
sourceMetadataOfType keyValue labelValue columnTypeValue attributeName aggregationValue factObject = do
  attribute <- findAttribute factObject attributeName
  pure
    ResolvedDisplayMetadata
      { metadataKey = keyValue
      , metadataLabel = labelValue
      , metadataColumnType = columnTypeValue
      , metadataSource = Just (ColumnRef "fact" (OT.source_column attribute))
      , metadataAggregation = aggregationValue
      }

maybeToList :: Maybe a -> [a]
maybeToList maybeValue =
  case maybeValue of
    Just value -> [value]
    Nothing -> []

firstJust :: [Maybe a] -> Maybe a
firstJust values =
  case values of
    [] -> Nothing
    Just value : _ -> Just value
    Nothing : remaining -> firstJust remaining

isPlayerRowObject :: OT.Object -> Bool
isPlayerRowObject OT.Object {OT.name = rowObjectName} =
  "player" `T.isInfixOf` T.toLower rowObjectName
