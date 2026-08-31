-- create table with identity column and primary key
SET ANSI_NULLS ON
SET QUOTED_IDENTIFIER ON
CREATE TABLE [dbo].[tdProducts_new](
	[ProductID] [int] NOT NULL IDENTITY(1,1),
	[ProductNumber] [nvarchar](30) NOT NULL,
	[Matchcode] [nvarchar](100) NULL,
	[BaseUnit] [nvarchar](10) NULL,
	[BaseDecimals] [smallint] NULL,
	[ProductGroup] [nvarchar](10) NULL,
	[MemoText] [ntext] NULL,
	[Name1] [nvarchar](100) NULL,
	[Name2] [nvarchar](100) NULL,
	[IsFavorite] [smallint] NULL,
	[Taxation] [int] NULL,
	[SalesUnit] [nvarchar](10) NULL,
	[ProductType] [int] NULL,
	[Warehouse] [int] NULL,
	[Stock] [money] NULL,
	[StockNotification] [money] NULL,
	[PriceUnit] [money] NULL,
	[ValuationPrice] [money] NULL,
	[IsManual] [smallint] NULL,
	[PriceBaseUnit] [nvarchar](10) NULL,
	[PriceBaseUnitConversion] [money] NULL,
	[FromImport] [int] NULL,
	[ProductERPID] [nvarchar](30) NULL,
	[ManufacturerID] [int] NULL,
	[AllowNegative] [smallint] NULL,
	[StockWithDrawalType] [smallint] NULL,
	[StockWithDrawalProcedure] [smallint] NULL,
	[RevenueBase] [smallint] NULL,
	[ReplaceMeanPurchasePrice] [smallint] NULL,
	[DivisionDependency] [smallint] NULL,
	[MainSupplier] [int] NULL,
	[LastSupplier] [int] NULL,
	[ProcurementTime] [int] NULL,
	[PurchaseProposalType] [smallint] NULL,
	[SalesPriceUnit] [nvarchar](10) NULL,
	[CostCenter] [int] NULL,
	[CostObjective] [int] NULL,
	[StockUnit] [nvarchar](10) NULL,
	[ExpenseCode] [nvarchar](5) NULL,
	[PurchaseAccountID] [int] NULL,
	[SalesAccountID] [int] NULL,
	[RevenueCode] [nvarchar](5) NULL,
	[GetsDiscount] [smallint] NULL,
	[GetsCommission] [smallint] NULL,
	[PriceGroup] [nvarchar](10) NULL,
	[ProductLength] [money] NULL,
	[ProductWidth] [money] NULL,
	[ProductHeight] [money] NULL,
	[ProductWeight] [money] NULL,
	[WeightUnit] [nvarchar](10) NULL,
	[ConsumptionUnit] [nvarchar](10) NULL,
	[ERPAvailability] [money] NULL,
	[IsExpired] [smallint] NULL,
	[ValidFrom] [datetime] NULL,
	[ValidTo] [datetime] NULL,
	[VariantPrices] [smallint] NULL,
	[HideCombinationPart] [smallint] NULL,
	[MatchcodeAdd] [nvarchar](50) NULL,
	[EANNumber] [nvarchar](20) NULL,
	[ProposalFactor] [money] NULL,
	[Division] [int] NULL,
	[CreationDate] [datetime] NULL,
	[ChangeDate] [datetime] NULL,
	[CreationUser] [nvarchar](5) NULL,
	[ChangeUser] [nvarchar](5) NULL,
	[ManufacturerNumber] [nvarchar](50) NULL,
	[ProductionUnit] [nvarchar](10) NULL,
	[DutyRateNumber] [nvarchar](30) NULL,
	[NotCashDiscountable] [smallint] NULL,
	[PriceMarkup] [money] NULL,
	[ProductCostAccountID] [int] NULL,
	[LockTypes] [int] NULL,
	[QuantityFormula] [int] NULL,
	[ProposalQuantity] [money] NULL,
	[UseForTimeInput] [smallint] NULL,
	[ABCCatery] [nvarchar](1) NULL,
	[InActive] [smallint] NULL,
	[PriceDecimals] [int] NULL,
	[ReplaceNullValuation] [int] NULL,
	[NoTurnover] [smallint] NULL,
	[ProposeAsProduct] [smallint] NULL,
	[ProductState] [int] NULL,
	[ProductStateText] [nvarchar](100) NULL,
	[ProposalFlag] [nvarchar](10) NULL,
	[OriginCountry] [nvarchar](5) NULL,
	[CalculationScheme] [int] NULL,
	[UseProductStockBooking] [smallint] NULL,
	[ProductStockAccountID] [int] NULL,
	[ReplaceTextPlaceholders] [smallint] NULL,
	[SalesBundleQuantity] [money] NULL,
	[StockNotificationMax] [money] NULL,
	[PPSVariantMatching] [smallint] NULL,
	[FromImportUpdated] [int] NULL,
	[IsInternalPos] [smallint] NULL,
	[NoPPSSubOrderCreating] [smallint] NULL,
	[ProductNetWeight] [money] NULL,
	[IntraZollEAN] [nvarchar](10) NULL,
	[IntraCommodityID] [int] NULL,
	[IntraCountry_OriginID] [nvarchar](5) NULL,
	[IntraRegion_OriginID] [int] NULL,
	[IntraCommodityDescription] [nvarchar](200) NULL,
	[IntraProceduralCode_Arrival] [int] NULL,
	[IntraProceduralCode_Dispatch] [int] NULL,
	[IntraNetMass] [money] NULL,
	[Intrakilogramm] [money] NULL,
	[IntraSupplementaryMass] [nvarchar](1) NULL,
	[IntraDeclarationValue] [money] NULL,
	[IntraDeclarationCurrency] [nvarchar](3) NULL,
	[IntraDiffMassUnitID] [int] NULL,
	[IntraDiffMassFactorDefault] [money] NULL,
	[IntraDeclarationImport] [money] NULL,
	[SalesMinQuantity] [money] NULL,
	[SalesValuationPriceFromStock] [smallint] NULL,
	[DGUNNumber] [nvarchar](4) NULL,
	[DGClass] [nvarchar](10) NULL,
	[DGClassificationCode] [nvarchar](10) NULL,
	[DGDescription] [nvarchar](max) NULL,
	[DGNOS] [nvarchar](max) NULL,
	[DGPackagingGroups] [nvarchar](10) NULL,
	[DGPackaging] [nvarchar](10) NULL,
	[DGSubClass1] [nvarchar](10) NULL,
	[DGSubClass2] [nvarchar](10) NULL,
	[DGTransportCatery] [nvarchar](1) NULL,
	[DGLQLimit] [money] NULL,
	[DGLimitedQuantity] [nvarchar](10) NULL,
	[DGProductLinkID] [int] NULL,
	[BulkyodsProductLinkID] [int] NULL,
	[MarketingScore] [money] NULL,
	[DGPackageDesc] [nvarchar](50) NULL,
	[DGTunnelRestriction] [nvarchar](10) NULL,
	[DGEurotunnel] [smallint] NULL,
	[ProductInventoryChangeAccountID] [int] NULL,
	[AccessFlag] [nvarchar](10) NULL,
	[NoTurnoverPurchase] [smallint] NULL,
--  CONSTRAINT [PK_tdProducts] PRIMARY KEY NONCLUSTERED 
-- (
-- 	[ProductID] ASC
-- )WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
-- ) 
ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF_tdProducts_IsFavorite]  DEFAULT ((0)) FOR [IsFavorite]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF_tdProducts_Taxation]  DEFAULT ((1)) FOR [Taxation]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF_tdProducts_ProductType]  DEFAULT ((1)) FOR [ProductType]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF_tdProducts_Stock]  DEFAULT ((0)) FOR [Stock]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF_tdProducts_StockNotification]  DEFAULT ((0)) FOR [StockNotification]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF_tdProducts_PriceUnit]  DEFAULT ((1)) FOR [PriceUnit]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF_tdProducts_ValuationPrice]  DEFAULT ((0)) FOR [ValuationPrice]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF_tdProducts_IsInternal]  DEFAULT ((0)) FOR [IsManual]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF_tdProducts_FromImport]  DEFAULT ((0)) FOR [FromImport]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF_tdProducts_AllowNegative]  DEFAULT ((2)) FOR [AllowNegative]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF_tdProducts_StockWithDrawalType]  DEFAULT ((2)) FOR [StockWithDrawalType]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF_tdProducts_RevenueBase]  DEFAULT ((1)) FOR [RevenueBase]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF_tdProducts_ReplaceMeanPurchasePrice]  DEFAULT ((0)) FOR [ReplaceMeanPurchasePrice]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF_tdProducts_DivisionDependency]  DEFAULT ((0)) FOR [DivisionDependency]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF_tdProducts_ProcurementTime]  DEFAULT ((0)) FOR [ProcurementTime]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF__tdProduct__Purch__4301EA8F]  DEFAULT ((0)) FOR [PurchaseProposalType]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF__tdProduct__GetsD__2F4FF79D]  DEFAULT ((-1)) FOR [GetsDiscount]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF__tdProduct__GetsC__30441BD6]  DEFAULT ((-1)) FOR [GetsCommission]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF__tdProduct__Produ__5CE1B823]  DEFAULT ((0)) FOR [ProductLength]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF__tdProduct__Produ__5DD5DC5C]  DEFAULT ((0)) FOR [ProductWidth]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF__tdProduct__Produ__5ECA0095]  DEFAULT ((0)) FOR [ProductHeight]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF__tdProduct__Produ__5FBE24CE]  DEFAULT ((0)) FOR [ProductWeight]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF__tdProduct__IsExp__7760A435]  DEFAULT ((0)) FOR [IsExpired]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF__tdProduct__Varia__7854C86E]  DEFAULT ((0)) FOR [VariantPrices]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF__tdProduct__HideC__0F382DC6]  DEFAULT ((0)) FOR [HideCombinationPart]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF__tdProduct__Propo__546C6DB3]  DEFAULT ((1)) FOR [ProposalFactor]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF__tdProduct__NotCa__6379A719]  DEFAULT ((0)) FOR [NotCashDiscountable]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF__tdProduct__InAct__12BEA5E7]  DEFAULT ((0)) FOR [InActive]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF__tdProduct__Price__1AE9D794]  DEFAULT ((-1)) FOR [PriceDecimals]
ALTER TABLE [dbo].[tdProducts_new] ADD  CONSTRAINT [DF_tdProducts_ReplaceNullValuation]  DEFAULT ((0)) FOR [ReplaceNullValuation]
ALTER TABLE [dbo].[tdProducts_new] ADD  DEFAULT ((0)) FOR [NoTurnover]
ALTER TABLE [dbo].[tdProducts_new] ADD  DEFAULT ((0)) FOR [ProposeAsProduct]
ALTER TABLE [dbo].[tdProducts_new] ADD  DEFAULT ((0)) FOR [UseProductStockBooking]
ALTER TABLE [dbo].[tdProducts_new] ADD  DEFAULT ((0)) FOR [ReplaceTextPlaceholders]
ALTER TABLE [dbo].[tdProducts_new] ADD  DEFAULT ((0)) FOR [PPSVariantMatching]
ALTER TABLE [dbo].[tdProducts_new] ADD  DEFAULT ((0)) FOR [IsInternalPos]
ALTER TABLE [dbo].[tdProducts_new] ADD  DEFAULT ((0)) FOR [NoPPSSubOrderCreating]
ALTER TABLE [dbo].[tdProducts_new] ADD  DEFAULT ((0)) FOR [IntraNetMass]
ALTER TABLE [dbo].[tdProducts_new] ADD  DEFAULT ((0)) FOR [Intrakilogramm]
ALTER TABLE [dbo].[tdProducts_new] ADD  DEFAULT ((0)) FOR [IntraDeclarationValue]
ALTER TABLE [dbo].[tdProducts_new] ADD  DEFAULT (N'EUR') FOR [IntraDeclarationCurrency]
ALTER TABLE [dbo].[tdProducts_new] ADD  DEFAULT ((1)) FOR [IntraDiffMassFactorDefault]
ALTER TABLE [dbo].[tdProducts_new] ADD  DEFAULT ((0)) FOR [IntraDeclarationImport]
ALTER TABLE [dbo].[tdProducts_new] ADD  DEFAULT ((0)) FOR [DGEurotunnel]
ALTER TABLE [dbo].[tdProducts_new] ADD  DEFAULT ((0)) FOR [NoTurnoverPurchase]
ALTER TABLE [dbo].[tdProducts_new]  WITH CHECK ADD  CONSTRAINT [FK_tdProducts_tdProductTypes] FOREIGN KEY([ProductType])
REFERENCES [dbo].[tdProductTypes] ([ProductTypeID])
ALTER TABLE [dbo].[tdProducts_new] CHECK CONSTRAINT [FK_tdProducts_tdProductTypes]
