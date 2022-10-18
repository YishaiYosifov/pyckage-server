from mysql.connector.cursor import CursorBase
from common.exceptions import InvalidData
from pydantic import BaseModel
from typing import Any

NOT_IN_TABLE = {"package_id", "requirements", "classifiers", "entry_points"}

class Package(BaseModel):
    def __init__(self, **data: Any) -> None:
        super().__init__(**data)

        from common.util import cursor

        if not self.requirements:
            cursor.execute("SELECT package, version FROM requirements WHERE name=%s", (self.name,))
            requirements = cursor.fetchall()

            self.requirements = requirements
        if not self.classifiers:
            cursor.execute("SELECT classifier FROM classifiers WHERE name=%s", (self.name,))
            classifiers = cursor.fetchall()
            classifiers = [classifier["classifier"] for classifier in classifiers]

            self.classifiers = classifiers

    package_id : int = None
    user_id : int

    repository : str
    version : str
    latest : bool

    release_date : int

    name : str

    description : str
    description_file : str

    author_email : str

    license : str

    entry_points : dict = {}
    requirements : list = []
    classifiers : list = []

    def insert(self, cursor : CursorBase) -> tuple[bool, tuple[str, int]]:
        from common.util import parse_requirements_mysql, parse_classifiers_mysql
        
        items = self.dict(exclude=NOT_IN_TABLE)
        keys, values = list(items.keys()), list(items.values())

        cursor.execute(f"INSERT INTO packages ({', '.join(keys)}) VALUES ({', '.join(['%s' for i in range(len(keys))])})", values)
        uploadedPackageID = cursor.lastrowid

        try: mysqlRequirements = parse_requirements_mysql(self.requirements, self, uploadedPackageID)
        except InvalidData as e: return False, e.args

        try: mysqlClassifiers = parse_classifiers_mysql(self.classifiers, self, uploadedPackageID)
        except InvalidData as e: return False, e.args

        if mysqlRequirements: cursor.executemany("INSERT INTO requirements (package_id, name, package, version) VALUES (%s, %s, %s, %s)", mysqlRequirements)
        if self.entry_points: cursor.executemany("INSERT INTO entry_points (package_id, name, entry_point) VALUES (%s, %s, %s)", list(self.entry_points.items()))
        if mysqlClassifiers: cursor.executemany("INSERT INTO classifiers (package_id, name, classifier) VALUES (%s, %s, %s)", mysqlClassifiers)

        return True, None

    def delete(self, cursor : CursorBase):
        cursor.execute("DELETE FROM requirements WHERE name=%s", (self.name,))
        cursor.execute("DELETE FROM classifiers WHERE name=%s", (self.name,))
        cursor.execute("DELETE FROM entry_points WHERE name=%s", (self.name,))
        cursor.execute("DELETE FROM packages WHERE name=%s", (self.name,))
    
    def delete_release(self, cursor : CursorBase):
        cursor.execute("DELETE FROM requirements WHERE package_id=%s", (self.package_id,))
        cursor.execute("DELETE FROM classifiers WHERE package_id=%s", (self.package_id,))
        cursor.execute("DELETE FROM entry_points WHERE package_id=%s", (self.package_id,))
        cursor.execute("DELETE FROM packages WHERE package_id=%s", (self.package_id,))

    def update(self, cursor : CursorBase, data : dict):
        updateColumns = [key + "=%s" for key in data.keys()]
        cursor.execute(f"UPDATE packages SET {' AND '.join(updateColumns)} WHERE package_id=%s", list(data.values()) + [self.package_id])