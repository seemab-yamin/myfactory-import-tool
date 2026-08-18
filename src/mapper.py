from typing import Dict

import pandas as pd

from logger import setup_logger

logger = setup_logger(__name__)


class FieldMapper:
    """Handles CSV to Myfactory field mapping"""

    def __init__(self, mapping: Dict[str, str]):
        self.mapping = mapping  # CSV_column -> Myfactory_field

    def map_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map CSV columns to Myfactory fields"""
        if df.empty:
            logger.warning("DataFrame is empty")
            return df

        # Create new DataFrame with mapped columns
        mapped_data = {}
        unmapped_columns = []

        for csv_col, myfactory_field in self.mapping.items():
            if csv_col in df.columns:
                mapped_data[myfactory_field] = df[csv_col]
                logger.debug(f"Mapped '{csv_col}' → '{myfactory_field}'")
            else:
                logger.warning(f"CSV column '{csv_col}' not found in file")
                unmapped_columns.append(csv_col)

        # Create DataFrame from mapped data
        result_df = pd.DataFrame(mapped_data)

        # Log results
        logger.info(
            f"Mapped {len(mapped_data)} columns, {len(unmapped_columns)} unmapped"
        )

        return result_df

    def preview_mapping(self, df: pd.DataFrame) -> None:
        """Preview the mapping (for dry-run)"""
        logger.info("=== MAPPING PREVIEW ===")
        logger.info(f"CSV Columns: {list(df.columns)}")
        logger.info(f"Mapping: {self.mapping}")

        if not df.empty:
            logger.info("\nFirst 3 rows preview:")
            print(df.head(3).to_string())
